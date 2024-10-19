import socket
import re
import os
from dotenv import load_dotenv
from task_manager import TaskManager
import threading
import time
from datetime import datetime, date, timedelta

class TwitchBot:
    def __init__(self):
        load_dotenv()
        self.username = os.getenv('TWITCH_BOT_USERNAME')
        self.oauth_token = os.getenv('TWITCH_OAUTH_TOKEN')
        self.channel = os.getenv('TWITCH_CHANNEL')
        self.admin_user = os.getenv('ADMIN_USER', 'fishermanguybro')  # New line to get admin user
        self.socket = socket.socket()
        self.connected = False
        self.task_manager = TaskManager('twitch_tasks.json')
        self.lurkers = set()  # New set to store lurkers

    def connect(self):
        try:
            self.socket = socket.socket()
            self.socket.connect(('irc.chat.twitch.tv', 6667))
            self.socket.send(f"PASS {self.oauth_token}\n".encode('utf-8'))
            self.socket.send(f"NICK {self.username}\n".encode('utf-8'))
            self.socket.send(f"JOIN #{self.channel}\n".encode('utf-8'))
            self.connected = True
            print("Connected to Twitch IRC")
        except Exception as e:
            print(f"Error connecting to Twitch IRC: {e}")
            self.connected = False

    def send_message(self, message):
        try:
            self.socket.send(f"PRIVMSG #{self.channel} :{message}\n".encode('utf-8'))
        except Exception as e:
            print(f"Error sending message: {e}")
            self.connected = False

    def run(self):
        if not self.connected:
            self.connect()

        # Start the task display thread
        threading.Thread(target=self.task_manager.display_tasks, daemon=True).start()

        # Start a thread to clean old tasks and reset daily stats
        threading.Thread(target=self.daily_maintenance, daemon=True).start()

        while True:
            if not self.connected:
                print("Not connected. Attempting to reconnect...")
                self.connect()
                if not self.connected:
                    time.sleep(5)  # Wait before trying to reconnect
                    continue

            try:
                response = self.socket.recv(2048).decode('utf-8')
                if not response:
                    print("Empty response received. Reconnecting...")
                    self.connected = False
                    continue

                if response.startswith('PING'):
                    self.socket.send("PONG\n".encode('utf-8'))

                elif len(response) > 0:
                    username_match = re.search(r":(\w+)!", response)
                    message_match = re.search(r"PRIVMSG.*:(.+)", response)
                    if username_match and message_match:
                        username = username_match.group(1)
                        message = message_match.group(1).strip()
                        self.handle_message(username, message)

            except Exception as e:
                print(f"Error in main loop: {e}")
                self.connected = False

    def daily_maintenance(self):
        while True:
            now = datetime.now()
            # Wait until the next day
            tomorrow = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
            time_to_wait = (tomorrow - now).total_seconds()
            time.sleep(time_to_wait)

            # Perform daily maintenance
            self.task_manager.clean_old_tasks()
            self.task_manager.reset_daily_stats()
            self.lurkers.clear()  # Clear the lurkers set at the start of a new day

    def handle_message(self, username, message):
        if message == '!hi':
            self.send_message('hello')
        elif message == '!lurk':
            self.lurkers.add(username)
            self.send_message(f"Thanks for lurking {username}!")
        elif message == '!lurkers':
            if self.lurkers:
                lurker_list = ", ".join(self.lurkers)
                self.send_message(f"Current lurkers: {lurker_list}")
            else:
                self.send_message("No one is currently lurking.")
        elif message.startswith('!task'):
            parts = message.split(maxsplit=2)
            if len(parts) == 1:
                # User just typed !task, show help message
                help_message = ("Task commands: !task add <description> | !task remove <id> | "
                                "!task complete <id> | !task list | !task stats")
                self.send_message(f"@{username} {help_message}")
            elif len(parts) < 2:
                return
            
            command = parts[1]
            if command == 'add':
                if len(parts) == 3:
                    task_id = self.task_manager.add_task(parts[2], username)
                    self.send_message(f"@{username} Task added with ID: {task_id}")
                else:
                    self.send_message(f"@{username} Please provide a task description.")
            elif command == 'remove':
                if len(parts) == 3:
                    if self.task_manager.remove_task(parts[2], username):
                        self.send_message(f"@{username} Task {parts[2]} removed")
                    else:
                        self.send_message(f"@{username} Task {parts[2]} not found or not assigned to you")
                else:
                    self.send_message(f"@{username} Please provide a task ID to remove.")
            elif command == 'complete':
                if len(parts) == 3:
                    if self.task_manager.complete_task(parts[2], username):
                        self.send_message(f"@{username} Task {parts[2]} marked as complete")
                    else:
                        self.send_message(f"@{username} Task {parts[2]} not found or not assigned to you")
                else:
                    self.send_message(f"@{username} Please provide a task ID to complete.")
            elif command == 'list':
                user_tasks = self.task_manager.get_user_tasks(username)
                task_list = self.task_manager.format_task_list(user_tasks)
                self.send_message(f"@{username} Your incomplete tasks: {task_list}")
            elif command == 'stats':
                stats = self.task_manager.get_user_stats(username)
                self.send_message(f"@{username} Your stats - Daily completed: {stats['daily']}, Total completed: {stats['total']}")
            elif command == 'wipe':
                if username == self.admin_user:
                    if len(parts) == 3:
                        user_to_wipe = parts[2]
                        wiped_count = self.task_manager.wipe_user_tasks(user_to_wipe)
                        self.send_message(f"@{username} Wiped {wiped_count} tasks for user {user_to_wipe}")
                    else:
                        self.send_message(f"@{username} Please provide a username to wipe tasks for.")
                else:
                    self.send_message(f"@{username} You don't have permission to use this command.")
            else:
                self.send_message(f"@{username} Invalid task command. Type !task for help.")

if __name__ == "__main__":
    bot = TwitchBot()
    bot.run()
