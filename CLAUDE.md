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

### Data Files

- **people_data.json** - Contains person information for form filling (name, surname, citizenship, email, phone, application_type)
- **days.json** - Stores availability scan results (date → time slots mapping)
- **playground.ipynb** - Session management experiments and API testing

### Key URLs and Endpoints

- Base URL: `https://olsztyn.uw.gov.pl/wizytakartapolaka/`
- Time slots API: `godziny_pokoj_A1.php` (POST with date parameter)
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

### Run availability scan only
```python
# In ajax2py.py, execute the bottom section
python ajax2py.py
```

### Run full automated booking
```python
# In interactions.py, main() function
python interactions.py
```

### Check specific dates
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

## Debugging

- Enable detailed logging by setting logging level to DEBUG
- Use `playground.ipynb` for testing API interactions
- Check browser console for JavaScript errors during automation
- Verify CAPTCHA API credentials if booking fails