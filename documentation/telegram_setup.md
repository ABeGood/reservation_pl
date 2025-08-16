# Telegram Bot Setup Guide

## Overview

The integrated Telegram bot provides real-time monitoring and control of the Polish Card availability monitor with instant notifications for slot discoveries, registration successes/failures, and system errors.

## Architecture

```
Main Process (integrated_bot.py)
├── TelegramBot (AsyncIO)
│   ├── Event Processor (Thread)
│   └── Bot Commands Handler
├── MonitorController
│   └── RealTimeAvailabilityMonitor (Thread)
└── EventQueue (Thread-safe communication)
```

## Environment Setup

### 1. Telegram Bot Token

1. Create a new bot with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow instructions
3. Copy the bot token

### 2. Environment Variables

Add to your `.env` file:

```env
# Telegram Configuration
TELEGRAM_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_USER_ID=your_telegram_user_id

# Database (already configured)
DATABASE_URL=your_postgres_url

# CAPTCHA API (already configured)
USER_ID=your_apitruecaptcha_userid
KEY=your_apitruecaptcha_key

# Optional: Auto-start monitor
AUTO_START_MONITOR=false
MONITOR_ROOM=A1
MONITOR_INTERVAL=0.5
```

### 3. Get Your Telegram User ID

1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. Send any message
3. Copy your user ID number
4. Add it to `TELEGRAM_ADMIN_USER_ID` in `.env`

## Running the System

### Start the Integrated Bot

```bash
python integrated_bot.py
```

This will start:
- Telegram bot with command handlers
- Event processing system for notifications
- Monitor controller (ready to start on command)

### Auto-start Monitor (Optional)

Set in `.env`:
```env
AUTO_START_MONITOR=true
MONITOR_ROOM=A1
MONITOR_INTERVAL=0.5
```

## Bot Commands

### Public Commands (All Users)

- `/start` - Welcome message and help
- `/help` - Show available commands
- `/status` - Monitor status and statistics
- `/pending` - Show pending registrants
- `/stats` - Database statistics

### Admin Commands (Admin Users Only)

- `/start_monitor [room] [interval]` - Start monitoring
  - Example: `/start_monitor A1 0.5`
  - Example: `/start_monitor A2 1.0`
- `/stop_monitor` - Stop monitoring
- `/restart_monitor` - Restart with current settings
- `/refresh_db` - Force refresh pending registrants

## Real-time Notifications

The bot automatically sends notifications for:

### 🎯 Slot Found
When new appointment slots are discovered

### ✅ Registration Success
When a registrant is successfully booked

### ❌ Registration Failed
When registration attempts fail

### 🚨 System Errors
Critical system errors and warnings

### 🚀 Monitor Status
When monitor starts/stops

## Features

### Parallel Processing
- Monitor runs independently from bot
- Non-blocking real-time notifications
- Thread-safe statistics tracking

### Smart Event Handling
- Priority-based event queue
- Automatic retry for critical events
- Rate limiting for Telegram API

### Database Integration
- Real-time pending registrant updates
- Comprehensive statistics
- Registration tracking

### Error Resilience
- Automatic bot restart on errors
- Monitor crash recovery
- Event queue overflow protection

## Usage Examples

### Start Monitoring Room A1
```
/start_monitor A1 0.5
```
Response: `🚀 Monitor started for room A1 (interval: 0.5s)`

### Check Status
```
/status
```
Response:
```
📊 Monitor Status

🟢 Status: Running
⏰ Uptime: 45 minutes
🏠 Room: A1
⚡ Check Interval: 0.5s
🤖 Auto Registration: ✅

📈 Statistics:
🔍 Checks: 5420
🎯 Slots Found: 12
✅ Registrations: 3
👥 Pending: 15
```

### View Pending Registrants
```
/pending
```
Response:
```
👥 Pending Registrants (15)

1. Jan Kowalski
   📧 jan@example.com
   📅 Wants month: 9

2. Anna Smith
   📧 anna@example.com
   📅 Wants month: 10
...
```

## Troubleshooting

### Bot Not Responding
1. Check `TELEGRAM_TOKEN` in `.env`
2. Verify bot is running: `python integrated_bot.py`
3. Check logs: `tail -f polish_card_bot.log`

### Admin Commands Not Working
1. Verify `TELEGRAM_ADMIN_USER_ID` is set correctly
2. Restart the bot after changing `.env`

### No Notifications
1. Check event processor is running
2. Verify monitor is started: `/status`
3. Check database has pending registrants: `/pending`

### Monitor Not Starting
1. Check database connection
2. Verify CAPTCHA API credentials
3. Check internet connection to target website

## Log Files

- `polish_card_bot.log` - All system logs
- Console output - Real-time status updates

## Security Notes

- Only admin users can control the monitor
- Bot token should be kept secret
- Database credentials are not exposed
- All registration data is encrypted in transit

## Performance

- Event queue processes ~1000 events/second
- Monitor checks availability every 0.5-3 seconds
- Telegram rate limiting: 30 messages/second
- Database queries are optimized and cached