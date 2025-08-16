import asyncio
import logging
from time import sleep
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, PhotoSize, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any, List, Optional
import json
import os
from dotenv import load_dotenv
import traceback
from datetime import datetime
import threading

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Import our custom classes
from database import DatabaseManager, get_pending_registrations
from monitor_controller import get_monitor_controller, start_monitor, stop_monitor, get_monitor_status, is_monitor_running
from monitor_events_manager import get_event_queue, EventType, MonitorEvent


class TelegramBot:
    def __init__(self, bot_token: str):
        self.bot = AsyncTeleBot(token=bot_token)
        self.db_manager = DatabaseManager()
        self.monitor_controller = get_monitor_controller()
        self.event_queue = get_event_queue()
        
        # Event processing
        self.event_processor_running = False
        self.event_processor_thread = None
        
        # Admin users (add your Telegram user ID here)
        self.admin_users = set()
        admin_user_id = os.environ.get("TELEGRAM_ADMIN_USER_ID")
        if admin_user_id:
            try:
                self.admin_users.add(int(admin_user_id))
            except ValueError:
                pass
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        self.register_handlers()
        self.start_event_processor()

    def start_event_processor(self):
        """Start event processor thread."""
        self.event_processor_running = True
        self.event_processor_thread = threading.Thread(
            target=self._process_events,
            name="EventProcessor",
            daemon=True
        )
        self.event_processor_thread.start()
        self.logger.info("Event processor started")

    def stop_event_processor(self):
        """Stop event processor thread."""
        self.event_processor_running = False
        if self.event_processor_thread:
            self.event_processor_thread.join(timeout=5.0)
        self.logger.info("Event processor stopped")

    def _process_events(self):
        """Process events from the monitor."""
        import asyncio
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            while self.event_processor_running:
                try:
                    event = self.event_queue.get_event(timeout=1.0)
                    if event:
                        loop.run_until_complete(self._handle_event(event))
                except Exception as e:
                    self.logger.error(f"Error processing event: {e}")
        finally:
            loop.close()

    async def _handle_event(self, event: MonitorEvent):
        """Handle a monitor event by sending Telegram notifications."""
        try:
            # Send to admin users
            for admin_id in self.admin_users:
                await self._send_event_notification(admin_id, event)
        except Exception as e:
            self.logger.error(f"Error handling event {event.event_type}: {e}")

    async def _send_event_notification(self, user_id: int, event: MonitorEvent):
        """Send event notification to specific user."""
        try:
            # Format message based on event type
            if event.event_type == EventType.ERROR:
                icon = "🚨"
                priority_icon = "🔥" if event.priority >= 4 else "⚠️"
                message = f"{icon}{priority_icon} *ERROR*\n{event.message}"
                
            elif event.event_type == EventType.SLOT_FOUND:
                icon = "🎯"
                slots = event.data.get('slots', [])
                message = f"{icon} *SLOTS FOUND*\n{event.message}\n\n"
                for slot in slots[:5]:  # Show first 5 slots
                    message += f"📅 {slot.get('date', 'N/A')} at {slot.get('time', 'N/A')}\n"
                
            elif event.event_type == EventType.REGISTRATION_SUCCESS:
                icon = "✅"
                registrant = event.data.get('registrant', {})
                slot = event.data.get('slot', {})
                message = f"{icon} *REGISTRATION SUCCESS*\n"
                message += f"👤 {registrant.get('name', '')} {registrant.get('surname', '')}\n"
                message += f"📅 {slot.get('date', 'N/A')} at {slot.get('time', 'N/A')}"
                
            elif event.event_type == EventType.REGISTRATION_FAILED:
                icon = "❌"
                registrant = event.data.get('registrant', {})
                message = f"{icon} *REGISTRATION FAILED*\n"
                message += f"👤 {registrant.get('name', '')} {registrant.get('surname', '')}\n"
                message += f"Error: {event.data.get('error', 'Unknown')}"
                
            elif event.event_type == EventType.MONITOR_STARTED:
                icon = "🚀"
                config = event.data.get('config', {})
                message = f"{icon} *MONITOR STARTED*\n"
                message += f"🏠 Room: {config.get('room', 'N/A')}\n"
                message += f"⚡ Interval: {config.get('check_interval', 'N/A')}s"
                
            elif event.event_type == EventType.MONITOR_STOPPED:
                icon = "⏹️"
                stats = event.data.get('final_stats', {})
                message = f"{icon} *MONITOR STOPPED*\n"
                if stats:
                    message += f"📊 Checks: {stats.get('checks_performed', 0)}\n"
                    message += f"🎯 Slots: {stats.get('slots_found', 0)}"
                
            else:
                # Generic message
                message = f"ℹ️ {event.message}"
            
            await self.bot.send_message(user_id, message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Failed to send notification to {user_id}: {e}")

    def run_bot(self):
        """Start the bot with improved error handling"""
        self.logger.info("Starting Polish Card reservation bot...")
        try:
            asyncio.run(self.bot.polling(non_stop=True, timeout=60, request_timeout=90))
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            self.stop_event_processor()
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error(f"Bot polling stopped due to an error: {e}\nFull traceback:\n{tb}")
            sleep(5)
            self.run_bot()

    def register_handlers(self):
        """Register all message handlers"""

        @self.bot.callback_query_handler(func=lambda call: True)
        async def handle_callback_query(call: CallbackQuery):
            """Handle all callback queries from inline keyboards"""
            # Messages handler



        @self.bot.message_handler(commands=['start'])
        async def handle_start(msg: Message):
            """Handle /start command"""
            welcome_text = (
                "🇵🇱 Polish Card Reservation Monitor Bot\n\n"
                "This bot monitors availability for Polish Card appointments "
                "and provides real-time notifications.\n\n"
                "📋 Available Commands:\n"
                "/status - Monitor status and statistics\n"
                "/pending - Show pending registrants\n"
                "/stats - Database statistics\n"
                "/help - Show this help message\n\n"
            )
            
            if msg.from_user.id in self.admin_users:
                welcome_text += (
                    "🔧 Admin Commands:\n"
                    "/start_monitor - Start availability monitoring\n"
                    "/stop_monitor - Stop monitoring\n"
                    "/restart_monitor - Restart monitoring\n"
                    "/refresh_db - Refresh pending registrants"
                )
            
            await self.bot.reply_to(msg, welcome_text)

        @self.bot.message_handler(commands=['help'])
        async def handle_help(msg: Message):
            """Handle /help command"""
            await handle_start(msg)

        @self.bot.message_handler(commands=['status'])
        async def handle_status(msg: Message):
            """Handle /status command"""
            status = get_monitor_status()
            
            status_text = "📊 *Monitor Status*\n\n"
            
            if status['running']:
                status_text += "🟢 *Status:* Running\n"
                if status['uptime_seconds']:
                    uptime_mins = int(status['uptime_seconds'] // 60)
                    status_text += f"⏰ *Uptime:* {uptime_mins} minutes\n"
            else:
                status_text += "🔴 *Status:* Stopped\n"
            
            config = status['config']
            status_text += f"🏠 *Room:* {config['room']}\n"
            status_text += f"⚡ *Check Interval:* {config['check_interval']}s\n"
            status_text += f"🤖 *Auto Registration:* {'✅' if config['auto_registration'] else '❌'}\n\n"
            
            if status['monitor_stats']:
                stats = status['monitor_stats']
                status_text += "📈 *Statistics:*\n"
                status_text += f"🔍 Checks: {stats.get('checks_performed', 0)}\n"
                status_text += f"🎯 Slots Found: {stats.get('slots_found', 0)}\n"
                status_text += f"✅ Registrations: {stats.get('successful_registrations', 0)}\n"
                status_text += f"👥 Pending: {stats.get('pending_registrants', 0)}\n"
            
            await self.bot.reply_to(msg, status_text, parse_mode='Markdown')

        @self.bot.message_handler(commands=['pending'])
        async def handle_pending(msg: Message):
            """Handle /pending command"""
            try:
                pending = get_pending_registrations()
                
                if not pending:
                    await self.bot.reply_to(msg, "📋 No pending registrants found.")
                    return
                
                response = f"👥 *Pending Registrants ({len(pending)})*\n\n"
                
                for i, registrant in enumerate(pending[:10], 1):  # Limit to first 10
                    response += f"{i}. {registrant.name} {registrant.surname}\n"
                    response += f"   📧 {registrant.email}\n"
                    response += f"   📅 Wants month: {registrant.desired_month}\n\n"
                
                if len(pending) > 10:
                    response += f"... and {len(pending) - 10} more\n"
                
                await self.bot.reply_to(msg, response, parse_mode='Markdown')
                
            except Exception as e:
                await self.bot.reply_to(msg, f"❌ Error fetching pending registrants: {str(e)}")

        @self.bot.message_handler(commands=['stats'])
        async def handle_stats(msg: Message):
            """Handle /stats command"""
            try:
                with DatabaseManager() as db:
                    stats = db.get_statistics()
                
                general = stats['general']
                response = "📊 *Database Statistics*\n\n"
                response += f"👥 Total Registrants: {general['total_registrants']}\n"
                response += f"✅ Registered: {general['registered_count']}\n"
                response += f"⏳ Pending: {general['pending_count']}\n\n"
                
                response += "🌍 *By Citizenship:*\n"
                for citizenship in stats['by_citizenship']:
                    response += f"• {citizenship['citizenship']}: {citizenship['count']} ({citizenship['registered']} registered)\n"
                
                response += "\n📅 *By Month:*\n"
                for month in stats['by_month']:
                    response += f"• Month {month['desired_month']}: {month['count']} ({month['registered']} registered)\n"
                
                await self.bot.reply_to(msg, response, parse_mode='Markdown')
                
            except Exception as e:
                await self.bot.reply_to(msg, f"❌ Error fetching statistics: {str(e)}")

        # Admin-only commands
        @self.bot.message_handler(commands=['start_monitor'])
        async def handle_start_monitor(msg: Message):
            """Handle /start_monitor command (admin only)"""
            if msg.from_user.id not in self.admin_users:
                await self.bot.reply_to(msg, "❌ This command is only available to administrators.")
                return
            
            if is_monitor_running():
                await self.bot.reply_to(msg, "⚠️ Monitor is already running.")
                return
            
            # Parse arguments (room, interval)
            args = msg.text.split()[1:] if len(msg.text.split()) > 1 else []
            room = args[0] if len(args) > 0 and args[0] in ['A1', 'A2'] else 'A1'
            interval = float(args[1]) if len(args) > 1 else 0.5
            
            success = start_monitor(room=room, check_interval=interval)
            
            if success:
                await self.bot.reply_to(msg, f"🚀 Monitor started for room {room} (interval: {interval}s)")
            else:
                await self.bot.reply_to(msg, "❌ Failed to start monitor. Check logs for details.")

        @self.bot.message_handler(commands=['stop_monitor'])
        async def handle_stop_monitor(msg: Message):
            """Handle /stop_monitor command (admin only)"""
            if msg.from_user.id not in self.admin_users:
                await self.bot.reply_to(msg, "❌ This command is only available to administrators.")
                return
            
            if not is_monitor_running():
                await self.bot.reply_to(msg, "⚠️ Monitor is not running.")
                return
            
            success = stop_monitor()
            
            if success:
                await self.bot.reply_to(msg, "⏹️ Monitor stopped successfully.")
            else:
                await self.bot.reply_to(msg, "❌ Failed to stop monitor. Check logs for details.")

        @self.bot.message_handler(commands=['restart_monitor'])
        async def handle_restart_monitor(msg: Message):
            """Handle /restart_monitor command (admin only)"""
            if msg.from_user.id not in self.admin_users:
                await self.bot.reply_to(msg, "❌ This command is only available to administrators.")
                return
            
            await self.bot.reply_to(msg, "🔄 Restarting monitor...")
            
            success = self.monitor_controller.restart_monitor()
            
            if success:
                await self.bot.reply_to(msg, "✅ Monitor restarted successfully.")
            else:
                await self.bot.reply_to(msg, "❌ Failed to restart monitor. Check logs for details.")

        @self.bot.message_handler(commands=['refresh_db'])
        async def handle_refresh_db(msg: Message):
            """Handle /refresh_db command (admin only)"""
            if msg.from_user.id not in self.admin_users:
                await self.bot.reply_to(msg, "❌ This command is only available to administrators.")
                return
            
            success = self.monitor_controller.force_database_refresh()
            
            if success:
                await self.bot.reply_to(msg, "🗄️ Database refreshed successfully.")
            else:
                await self.bot.reply_to(msg, "⚠️ Monitor not running or refresh failed.")


        @self.bot.message_handler(
            func=lambda msg: msg.text is not None and '/' not in msg.text,
        )
        async def handle_message(msg: Message):
            """Handle regular text messages"""
            user_id = msg.from_user.id
            message_text = msg.text.strip()
            
            # Simple echo for unrecognized commands
            await self.bot.reply_to(msg, "Use /help to see available commands.")
            

# Usage example
if __name__ == "__main__":
    
    # Initialize and run bot
    try:
        bot = TelegramBot(
            bot_token=BOT_TOKEN,
        )
        bot.run_bot()
    except Exception as e:
        print(f"Failed to start bot: {e}")
        print("Make sure you've set your BOT_TOKEN correctly!")