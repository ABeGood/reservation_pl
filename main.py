"""
Integrated Polish Card Reservation Bot with Monitor.
Runs both the Telegram bot and RealTimeAvailabilityMonitor together.
"""

import asyncio
import logging
import threading
import time
import os
from dotenv import load_dotenv

from tg_bot import TelegramBot
from monitor_controller import get_monitor_controller
from monitor_events_manager import get_event_queue, emit_monitor_started


def setup_logging():
    """Configure logging for the integrated system."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('polish_card_bot.log')
        ]
    )


def main():
    """Main entry point for the integrated bot system."""
    load_dotenv()
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("🚀 Starting Polish Card Reservation Bot System")
    
    # Check environment variables
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("❌ TELEGRAM_TOKEN environment variable not found")
        return
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable not found")
        return
    
    admin_user_id = os.environ.get("TELEGRAM_ADMIN_USER_ID")
    if not admin_user_id:
        logger.warning("⚠️ TELEGRAM_ADMIN_USER_ID not set - admin commands will be unavailable")
    
    try:
        # Initialize Telegram bot
        logger.info("📱 Initializing Telegram bot...")
        bot = TelegramBot(bot_token)
        
        # Initialize monitor controller (global instance)
        logger.info("🔍 Initializing monitor controller...")
        monitor_controller = get_monitor_controller()
        
        # Start event queue processing (already started in TelegramBot.__init__)
        event_queue = get_event_queue()
        logger.info(f"📡 Event queue initialized - stats: {event_queue.get_stats()}")
        
        # Start the bot in a separate thread
        bot_thread = threading.Thread(
            target=bot.run_bot,
            name="TelegramBot",
            daemon=True
        )
        bot_thread.start()
        logger.info("✅ Telegram bot started")
        
        # Optional: Auto-start monitor
        auto_start_monitor = os.environ.get("AUTO_START_MONITOR", "false").lower() == "true"
        if auto_start_monitor:
            logger.info("🔄 Auto-starting monitor...")
            room = os.environ.get("MONITOR_ROOM", "A1")
            interval = float(os.environ.get("MONITOR_INTERVAL", "0.5"))
            
            success = monitor_controller.start_monitor(
                room=room,
                check_interval=interval,
                auto_registration=True
            )
            
            if success:
                logger.info(f"✅ Monitor auto-started for room {room}")
            else:
                logger.error("❌ Failed to auto-start monitor")
        
        # Main loop - keep the program running
        logger.info("🎯 System ready! Use Telegram commands to control the monitor.")
        logger.info("📋 Available commands: /start, /status, /pending, /stats")
        if admin_user_id:
            logger.info("🔧 Admin commands: /start_monitor, /stop_monitor, /restart_monitor, /refresh_db")
        logger.info("Press Ctrl+C to stop the system")
        
        try:
            while True:
                time.sleep(1)
                
                # Check if bot thread is still alive
                if not bot_thread.is_alive():
                    logger.error("❌ Telegram bot thread died")
                    break
                
        except KeyboardInterrupt:
            logger.info("⏹️ Shutdown signal received")
            
    except Exception as e:
        logger.error(f"💥 System startup failed: {e}", exc_info=True)
        return
    
    finally:
        # Cleanup
        logger.info("🧹 Cleaning up...")
        
        # Stop monitor if running
        if monitor_controller.is_running():
            logger.info("⏹️ Stopping monitor...")
            monitor_controller.stop_monitor()
        
        # Stop event processor
        if hasattr(bot, 'stop_event_processor'):
            logger.info("⏹️ Stopping event processor...")
            bot.stop_event_processor()
        
        logger.info("✅ Cleanup completed. Goodbye!")


if __name__ == "__main__":
    main()