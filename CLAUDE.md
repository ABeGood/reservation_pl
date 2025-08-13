# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Polish Card appointment reservation automation system for the Olsztyn office website. The project consists of three main Python modules that work together to automate the process of finding and booking appointments for Polish Card applications.

## Architecture

### Core Components

1. **ajax2py.py** - Main API interaction module
   - `get_available_times()` - Replicates AJAX calls to fetch appointment slots
   - `parse_time_slots()` - Extracts available times from HTML responses
   - `check_multiple_days_with_times()` - Bulk availability checker for date ranges
   - `send_registration_request()` - Submits booking requests (incomplete)

2. **interactions.py** - Browser automation module
   - `PolishCardFormFiller` - Basic form filling with Selenium
   - `DatePickerScanner` - Advanced calendar scanning and auto-booking system
   - Main workflow: Open datepicker → Click date → Check slots → Attempt booking

3. **capcha.py** - CAPTCHA solving integration
   - `solve()` - Solves CAPTCHA from image file
   - `solve_base64()` - Solves CAPTCHA from base64 string
   - Uses apitruecaptcha.org API service

4. **realtime_availability_monitor.py** - Real-time monitoring system ⭐ NEW
   - `RealTimeAvailabilityMonitor` - High-frequency availability checker with parallel processing
   - Dynamic datepicker configuration extraction from webpage
   - Monitors only from today to last available date in datepicker
   - Supports both A1 and A2 room endpoints
   - Parallel date checking with ThreadPoolExecutor (up to 8x faster)
   - Thread-safe statistics tracking and comprehensive logging

### Data Files

- **people_data.json** - Contains person information for form filling (name, surname, citizenship, email, phone, application_type)
- **days.json** - Stores availability scan results (date → time slots mapping)
- **playground.ipynb** - Session management experiments and API testing

### Key URLs and Endpoints

- Base URL: `https://olsztyn.uw.gov.pl/wizytakartapolaka/`
- Room A1 - Page: `pokoj_A1.php`, Time slots API: `godziny_pokoj_A1.php` (POST with date parameter)
- Room A2 - Page: `pokoj_A2.php`, Time slots API: `godziny_pokoj_A2.php` (POST with date parameter)
- Form submission: `send.php`
- CAPTCHA endpoint: `securimage/securimage_show.php`

## Environment Setup

### Required Dependencies
- `requests` - HTTP client for API calls
- `selenium` - Browser automation
- `python-dotenv` - Environment variable management
- `base64` - CAPTCHA image encoding

### Environment Variables
Create a `.env` file with:
```
USER_ID=your_apitruecaptcha_userid
KEY=your_apitruecaptcha_key
```

### Chrome WebDriver
The system requires ChromeDriver for Selenium automation. Can be auto-detected or specified via path.

## Common Operations

### Real-time availability monitoring ⭐ RECOMMENDED
```bash
python realtime_availability_monitor.py
```
- Dynamically extracts datepicker constraints from webpage
- Monitors only dates from today to last available date
- **Parallel processing**: Up to 8 concurrent date checks (8x faster than sequential)
- **Server-friendly**: 0.2s delay per worker, limited to 8 max concurrent connections
- Supports both A1 and A2 room endpoints
- Thread-safe statistics and comprehensive real-time logging
- Saves results to timestamped JSON files

### Run availability scan only (legacy)
```python
# In ajax2py.py, execute the bottom section
python ajax2py.py
```

### Run full automated booking with browser
```python
# In interactions.py, main() function
python interactions.py
```

### Check specific dates (legacy)
Modify the date range in `ajax2py.py` line 108:
```python
check_multiple_days_with_times("2025-08-05", "2025-11-30", base_url)
```

## Important Implementation Notes

### Session Management
- PHPSESSID cookies are required for form submission
- Session must be obtained by visiting CAPTCHA endpoint first
- See `playground.ipynb` for session handling experiments

### CAPTCHA Integration
- Uses external API service (apitruecaptcha.org)
- Requires valid API credentials in environment
- Base64 encoding is used for image data transfer

### Browser Automation Patterns
- DatePickerScanner follows specific workflow: datepicker click → date selection → slot checking
- Anti-automation measures are bypassed with specific Chrome options
- Form fields have specific IDs: `imie`, `nazwisko`, `obywatel`, `email`, `telefon`, `rodzaj`

### Data Processing
- Time slots are extracted from HTML using regex patterns
- Polish month names are mapped to numeric values
- Results are saved to timestamped JSON files

### Real-time Monitor Features
- **Dynamic Configuration**: Scrapes `disabledDays`, `minDate`, `maxDate` from webpage JavaScript
- **Smart Date Range**: Only checks from today to last available date (ignores past dates)
- **Parallel Processing**: ThreadPoolExecutor with up to 8 workers for concurrent date checking
- **Server Courtesy**: 0.2s delay per worker, thread-safe request limiting
- **Performance**: Up to 8x faster than sequential checking while maintaining server friendliness
- **Comprehensive Logging**: Real-time progress tracking with completion counts and slot detection
- **Multi-Endpoint Support**: Automatically switches between A1/A2 endpoints based on user choice
- **Fallback Handling**: Uses reasonable defaults if webpage scraping fails
- **Thread Safety**: Concurrent statistics tracking with proper locking mechanisms

## Debugging

- Enable detailed logging by setting logging level to DEBUG
- Use `playground.ipynb` for testing API interactions
- Check browser console for JavaScript errors during automation
- Verify CAPTCHA API credentials if booking fails
- **Real-time monitor**: All activity is logged in info mode by default - watch console output for detailed parallel checking progress and completion statistics