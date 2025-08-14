# Registration Request Flow Documentation

## Overview
This document describes the registration request flow implemented in `ajax2py.py` for submitting Polish Card appointment reservations. The flow handles session management, form data preparation, and response parsing to automate the registration process.

## Main Functions

### `send_registration_request()`
The primary function for submitting registration requests to the Polish Card appointment system.

#### Function Signature
```python
def send_registration_request(
    base_url: str, 
    registrant_data: dict, 
    timeslot_data: dict, 
    captcha_code: str, 
    session_id: str = None
) -> dict
```

#### Parameters

**base_url** (str)
- Base URL of the appointment system
- Example: `"https://olsztyn.uw.gov.pl/wizytakartapolaka/"`
- Function handles both with and without trailing slash

**registrant_data** (dict)
- Personal information dictionary with required keys:
  - `name` (str): First name, max 15 characters
  - `surname` (str): Last name, max 20 characters  
  - `citizenship` (str): Must be one of:
    - `"Białoruś"` (Belarus)
    - `"Rosja"` (Russia)
    - `"Ukraina"` (Ukraine)
    - `"status bezpaństwowca"` (stateless person status)
  - `email` (str): Valid email address
  - `phone` (str): Phone number (digits only)
  - `application_type` (str): Must be one of:
    - `"osoba dorosła"` (adult person)
    - `"osoba dorosła i małoletnie dzieci"` (adult and minor children)
    - `"małoletni"` (minor)

**timeslot_data** (dict)
- Appointment slot information with required keys:
  - `date` (str): Date in YYYY-MM-DD format
  - `timeslot_value` (str): Full timeslot value (e.g., `"A209:00"`)

**captcha_code** (str)
- Solved CAPTCHA code, max 6 characters
- Case-sensitive

**session_id** (str, optional)
- PHPSESSID cookie value
- If None, function will automatically obtain one via `get_session_id()`

#### Return Value
Returns a dictionary with the following structure:

**Success Response:**
```python
{
    'success': True,
    'status_code': 200,
    'response_text': '...',
    'url': 'final_redirect_url',
    'cookies': {...},
    'payload_sent': {...},
    'message': 'Registration appears successful'
}
```

**Error Response:**
```python
{
    'success': False,
    'status_code': 400,  # or other error code
    'response_text': '...',
    'url': 'error_page_url',
    'cookies': {...},
    'payload_sent': {...},
    'message': 'Registration failed - check response for details'
}
```

**Network Error Response:**
```python
{
    'success': False,
    'error': 'Connection timeout',
    'message': 'Request failed',
    'payload_sent': {...}
}
```

## Registration Flow Steps

### 1. URL Construction
- Constructs the submission URL: `{base_url}send.php`
- Handles both trailing slash scenarios

### 2. Session Management
- If `session_id` not provided, calls `get_session_id()` to obtain one
- PHPSESSID cookie is essential for form submission

### 3. Payload Construction
Maps input data to form fields:
```python
payload = {
    "imie": registrant_data['name'],
    "nazwisko": registrant_data['surname'], 
    "obywatelstwo": registrant_data['citizenship'],
    "email": registrant_data['email'],
    "telefon": registrant_data['phone'],
    "rodzaj_wizyty": registrant_data['application_type'],
    "datepicker": timeslot_data['date'],           # YYYY-MM-DD
    "godzina": timeslot_data['timeslot_value'],    # A1HH:MM or A2HH:MM
    "captcha_code": captcha_code
}
```

### 4. HTTP Headers
Mimics browser behavior with comprehensive headers:
```python
headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': base_url,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pl,en-US;q=0.7,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}
```

### 5. Request Submission
- POST request with 30-second timeout
- Allows redirects to handle success/error pages
- Includes session cookies

### 6. Response Analysis
- Checks HTTP status code
- Searches response text for success/error indicators
- Polish phrases for success: `'rezerwacja została'`, `'potwierdzenie'`, `'sukces'`, `'zarezerwowano'`
- Polish/English phrases for errors: `'błąd'`, `'error'`, `'nieprawidłowy'`, `'captcha'`

## Session Management Function

### `get_session_id()`
Auxiliary function to obtain a valid PHPSESSID by visiting the CAPTCHA endpoint.

#### Function Signature
```python
def get_session_id(base_url: str) -> str
```

#### Process
1. Constructs CAPTCHA URL: `{base_url}securimage/securimage_show.php`
2. Makes GET request with minimal headers
3. Extracts PHPSESSID from response cookies
4. Returns session ID or None if failed

#### Usage
```python
session_id = get_session_id("https://olsztyn.uw.gov.pl/wizytakartapolaka/")
# Returns: "9c61b45f8b29a0e306d5c39d2fea62a7" or None
```

## Integration with Other Components

### Integration with RealTimeAvailabilityMonitor
The function is designed to work seamlessly with output from `RealTimeAvailabilityMonitor.get_timeslots()`:

```python
# Get available slots
monitor = RealTimeAvailabilityMonitor()
slots_data = monitor.get_timeslots()

# Use first available slot for registration
if slots_data['registration_data']:
    slot = slots_data['registration_data'][0]
    
    timeslot_data = {
        'date': slot['date'],
        'timeslot_value': slot['timeslot_value']
    }
    
    result = send_registration_request(
        base_url="https://olsztyn.uw.gov.pl/wizytakartapolaka/",
        registrant_data=person_data,
        timeslot_data=timeslot_data,
        captcha_code=solved_captcha
    )
```

### Integration with CAPTCHA Solving
Works with `capcha.py` module for automated CAPTCHA solving:

```python
from capcha import solve_base64

# Get session and CAPTCHA image
session_id = get_session_id(base_url)
captcha_image_url = f"{base_url}securimage/securimage_show.php"
# ... get image as base64 ...
captcha_code = solve_base64(image_base64)

# Submit registration
result = send_registration_request(
    base_url=base_url,
    registrant_data=person_data,
    timeslot_data=slot_data,
    captcha_code=captcha_code,
    session_id=session_id
)
```

## Error Handling

### Network Errors
- Connection timeouts
- DNS resolution failures
- SSL certificate errors
- Returns structured error response with exception details

### HTTP Errors
- 4xx client errors (invalid data, session expired)
- 5xx server errors (server overload, maintenance)
- Returns status code and response content for debugging

### Application Errors
- Invalid CAPTCHA
- Appointment slot no longer available
- Validation errors from form fields
- Detected through response text analysis

### Session Errors
- Expired PHPSESSID
- Missing session cookie
- Automatic session renewal attempted via `get_session_id()`

## Usage Examples

### Basic Registration
```python
from ajax2py import send_registration_request

base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"

registrant_data = {
    'name': 'Jan',
    'surname': 'Kowalski',
    'citizenship': 'Ukraina',
    'email': 'jan.kowalski@example.com',
    'phone': '123456789',
    'application_type': 'osoba dorosła'
}

timeslot_data = {
    'date': '2025-08-15',
    'timeslot_value': 'A209:00'
}

result = send_registration_request(
    base_url=base_url,
    registrant_data=registrant_data,
    timeslot_data=timeslot_data,
    captcha_code='ABC123'
)

if result['success']:
    print("Registration successful!")
else:
    print(f"Registration failed: {result['message']}")
```

### With Custom Session Management
```python
from ajax2py import send_registration_request, get_session_id

# Get fresh session
session_id = get_session_id(base_url)
print(f"Got session: {session_id}")

# Use session for registration
result = send_registration_request(
    base_url=base_url,
    registrant_data=registrant_data,
    timeslot_data=timeslot_data,
    captcha_code=captcha_code,
    session_id=session_id
)
```

## Security Considerations

### Session Security
- PHPSESSID cookies are obtained legitimately through CAPTCHA endpoint
- Sessions expire after server-defined timeout
- No session hijacking or reuse of expired sessions

### Rate Limiting
- 30-second timeout prevents indefinite hanging
- Natural rate limiting through CAPTCHA requirement
- Server-friendly request patterns

### Data Validation
- Client-side validation of required fields
- Server performs final validation
- No injection attacks through proper form encoding

## Performance Notes

### Request Timing
- Average response time: 2-5 seconds
- Timeout after 30 seconds
- Session establishment adds ~1 second overhead

### Error Recovery
- Automatic session renewal on failure
- Structured error responses for retry logic
- Comprehensive logging through response details

### Server Compatibility
- Handles redirects for success/error pages
- Supports gzip compression
- Compatible with standard PHP session management