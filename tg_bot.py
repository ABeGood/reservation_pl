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

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Import our custom classes
from database import DatabaseManager, get_pending_registrations
from monitor_controller import get_monitor_controller, start_monitor, stop_monitor, get_monitor_status, is_monitor_running
from monitor_events_manager import get_event_queue, EventType, MonitorEvent


class TelegramBot:
    def __init__(self, bot_token: str):
        self.bot = AsyncTeleBot(
            token=bot_token,
            state_storage=None  # Disable state storage for better stability
        )
        self.db_manager = DatabaseManager()
        self.monitor_controller = get_monitor_controller()
        self.event_queue = get_event_queue()
        
        # Event processing
        self.event_processor_running = False
        self.event_processor_task = None
        
        # Admin users (add your Telegram user ID here)
        self.admin_users = set()
        admin_user_id = os.environ.get("TELEGRAM_ADMIN_USER_ID")
        if admin_user_id:
            try:
                self.admin_users.add(int(admin_user_id))
            except ValueError:
                pass
        
        # Admin group ID
        self.admin_group_id = None
        admin_group_id = os.environ.get("TELEGRAM_ADMIN_GROUP_ID")
        if admin_group_id:
            try:
                self.admin_group_id = int(admin_group_id)
            except ValueError:
                pass
        
        from logging_config import get_logger
        self.logger = get_logger(__name__)

        # Log configuration
        self.logger.info(f"TelegramBot initialized with {len(self.admin_users)} admin users")
        if self.admin_group_id:
            self.logger.info(f"Admin group configured: {self.admin_group_id}")
        else:
            self.logger.info("No admin group configured")

        self.register_handlers()

    async def start_event_processor(self):
        """Start event processor as asyncio task."""
        self.event_processor_running = True
        self.event_processor_task = asyncio.create_task(self._process_events_async())
        self.logger.info("Event processor started")

    async def stop_event_processor(self):
        """Stop event processor task."""
        self.event_processor_running = False
        if self.event_processor_task:
            self.event_processor_task.cancel()
            try:
                await self.event_processor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Event processor stopped")

    async def _process_events_async(self):
        """Process events in the main asyncio loop."""
        while self.event_processor_running:
            try:
                # Non-blocking check for events
                event = self.event_queue.get_event(timeout=0.1)
                if event:
                    await self._handle_event(event)
                # Small delay to allow other tasks to run
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
                await asyncio.sleep(1.0)  # Longer delay on error

    async def _handle_event(self, event: MonitorEvent):
        """Handle a monitor event by sending Telegram notifications."""
        try:
            # Send to admin users
            for admin_id in self.admin_users:
                await self._send_event_notification(admin_id, event)
            
            # Send to admin group if configured
            if self.admin_group_id:
                await self._send_event_notification(self.admin_group_id, event)
                self.logger.debug(f"Event {event.event_type.value} sent to admin group {self.admin_group_id}")
        except Exception as e:
            self.logger.error(f"Error handling event {event.event_type}: {e}")

    async def _send_event_notification(self, chat_id: int, event: MonitorEvent):
        """Send event notification to specific user or group."""
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
                    message += f"📊 Day checks: {stats.get('checks_performed', 0)}\n"
                    message += f"🎯 Slots: {stats.get('slots_found', 0)}"
                
            else:
                # Generic message
                message = f"ℹ️ {event.message}"
            
            await self.bot.send_message(chat_id, message, parse_mode='Markdown')
            
        except Exception as e:
            # Determine if it's a group or user for better logging
            chat_type = "group" if chat_id < 0 else "user"
            self.logger.error(f"Failed to send notification to {chat_type} {chat_id}: {e}")

    async def _run_bot_async(self):
        """Async wrapper to start both bot polling and event processing."""
        # Start event processor
        await self.start_event_processor()
        
        try:
            # Start bot polling with improved timeout settings
            await self.bot.polling(
                non_stop=True, 
                timeout=20,  # Shorter timeout for long polling
                request_timeout=30,  # Shorter request timeout
                allowed_updates=None,
                skip_pending=True  # Skip old messages on restart
            )
        finally:
            # Ensure event processor is stopped
            await self.stop_event_processor()

    def run_bot(self):
        """Start the bot with improved error handling"""
        self.logger.info("Starting Polish Card reservation bot...")
        try:
            asyncio.run(self._run_bot_async())
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error(f"Bot polling stopped due to an error: {e}\nFull traceback:\n{tb}")
            self.logger.error("Bot failed to start properly. Program will exit.")

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
                    # response += f"   📧 {registrant.email}\n"
                    response += f"   📅 Registration month: {registrant.desired_month}\n\n"
                
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
                self.logger.info(f"🚀 Monitor started for room {room} (interval: {interval}s)")
            else:
                await self.bot.reply_to(msg, "❌ Failed to start monitor. Check logs for details.")
                self.logger.error("❌ Failed to start monitor. Check logs for details.")


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
                self.logger.info("⏹️ Monitor stopped successfully.")
            else:
                await self.bot.reply_to(msg, "❌ Failed to stop monitor. Check logs for details.")
                self.logger.error("❌ Failed to stop monitor. Check logs for details.")

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
                self.logger.error("❌ Failed to restart monitor. Check logs for details.")

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
            

# # Usage example
# if __name__ == "__main__":
    
#     # Initialize and run bot
#     try:
#         bot = TelegramBot(
#             bot_token=BOT_TOKEN,
#         )
#         bot.run_bot()
#     except Exception as e:
#         from logging_config import get_logger
#         logger = get_logger(__name__)
#         logger.error(f"Failed to start bot: {e}")
#         logger.error("Make sure you've set your BOT_TOKEN correctly!")