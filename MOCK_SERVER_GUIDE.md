# Mock Registration Server Guide

This mock server replicates the complete functionality of the original Polish Card registration website for testing purposes.

## Features

✅ **Complete endpoint coverage:**
- Main registration pages (`pokoj_A1.php`, `pokoj_A2.php`)
- Timeslots API (`godziny_pokoj_A1.php`, `godziny_pokoj_A2.php`)
- CAPTCHA generation (`securimage/securimage_show.php`)
- Form submission (`send.php`)
- Static assets (CSS, images)

✅ **Realistic responses:**
- Same HTML structure as original
- Proper Polish error messages
- Authentic success page format
- Working CAPTCHA validation

✅ **Test coverage:**
- All success cases
- Error scenarios (bad CAPTCHA, unavailable slots)
- Edge cases (empty dates, invalid data)
- API endpoints for debugging

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements_mock.txt
```

### 2. Start Mock Server
```bash
python mock_server.py
```

The server will start at `http://localhost:5000`

### 3. Update Your Test Scripts
Point your existing code to the mock server:

```python
# Instead of:
base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"

# Use:
base_url = "http://localhost:5000/"
```

## Testing

### Automated Tests
```bash
python test_mock_server.py
```

This will test:
- Server availability
- Timeslots API for both rooms
- CAPTCHA generation and solving
- Complete registration flow
- Error handling
- API endpoints

### Manual Testing

**Main Pages:**
- http://localhost:5000 - Server index
- http://localhost:5000/pokoj_A1.php - Room A1 form
- http://localhost:5000/pokoj_A2.php - Room A2 form

**API Endpoints:**
- GET /api/registrations - View all successful registrations
- GET /api/timeslots - View current slot availability
- POST /api/reset - Reset all data for clean testing

## Available Test Data

### Pre-configured Dates with Slots:
- `2025-06-16`: 09:00, 10:00, 11:00
- `2025-06-26`: 09:00 (single slot for testing)
- `2025-07-09`: 09:00, 10:00 (good for registration tests)
- `2025-07-10`: 09:00, 10:00, 11:00
- `2025-06-25`: [] (empty - for testing "no slots" case)

### Test Registration Data:
```python
registrant_data = {
    'imie': 'Elena',
    'nazwisko': 'Kovalenko', 
    'obywatelstwo': 'Białoruś',
    'email': 'e.kovalenko2024@gmail.com',
    'telefon': '667889123',
    'rodzaj_wizyty': 'osoba dorosła'
}

timeslot_data = {
    'date': '2025-07-10',
    'timeslot_value': 'A209:00'  # Room A2, 09:00
}
```

## Integration with Existing Code

The mock server is designed to work seamlessly with your existing modules:

### With `ajax2py.py`:
```python
from ajax2py import get_timeslots_for_single_date

# This will work unchanged with mock server
date_str, slots = get_timeslots_for_single_date(
    "2025-07-09", 
    "http://localhost:5000/", 
    "godziny_pokoj_A2.php"
)
```

### With `realtime_availability_monitor.py`:
```python
# Just change the page_url in the constructor:
monitor = RealTimeAvailabilityMonitor("http://localhost:5000/pokoj_A1.php")
monitor.base_url = "http://localhost:5000/"
```

### With Registration Code:
```python
from ajax2py import send_registration_request_with_retry

# This will work with full CAPTCHA solving
result = send_registration_request_with_retry(
    base_url="http://localhost:5000/",
    registrant_data=registrant_data,
    timeslot_data=timeslot_data,
    max_retries=3
)
```

## Response Format Examples

### Success Response (matches original):
```html
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <link href="style.css" rel="stylesheet" type="text/css" />
</head>
<body>
    <table style='border: 1px solid black; width:340px'>
        <tr><td>
            <center>
                <img src="graf\\grafika.png" alt="Logo WMUW w Olsztynie" width="170" height="40" align="rightt">
                <hr width="285" color="#545454"/>
                Wydział Spraw Obywatelskich i Cudzoziemców<br />
                Rezerwacja terminu wizyty - Obywatelstwo<br />
                Przedłużenie ważności, wydanie duplikatu, zmiana danych Karty Polaka<br />
                <hr width="285" color="#545454"/>
            </center>
            <p class="a">
                Dane rejestracyjne:&nbsp<t class='text'>Elena &nbsp Kovalenko</t><br />
                Adres e-mail-<t class='text'>&nbsp;e.kovalenko2024@gmail.com</t><br />
                Telefon-<t class='text'>&nbsp;667889123</t><br />
                Data rezerwacji,godzina,stanowisko-<br>
                <t class='text'>2025-07-10 &nbsp 09:00 &nbsp A2 pokoj 25</t><br />
                Obywatelstwo -<t class='text'>&nbsp;Białoruś</t><br />
                Dotyczy -<t class='text'>&nbsp;osoba dorosła</t><br />
                Kod zgłoszenia-<t class='text'>&nbsp;a4b34f</t><br />
            </p>
            <center>
                <hr width="285" color="#545454"/>
                <a href="#" onclick="javascript:window.print()">Drukuj | </a>
                <a href='./rezerwacje.php'>Główna |</a>
                <a href='./pokoj_A2.php'>Wstecz</a><br />
            </center>
            <hr width="285" color="#545454"/>
        </td></tr>
    </table>
</body>
</html>
```

### Bad CAPTCHA Response:
```html
<html>
<head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <link href="style.css" rel="stylesheet" type="text/css" />
</head>
<body>
    <a href='./rezerwacje.php'>wstecz</a><br />
    kod z obrazka przepisany przez ciebie jest nieprawidłowy!!
</body>
</html>
```

## Test Scenarios Covered

1. **Happy Path**: Complete registration with valid data
2. **CAPTCHA Validation**: Wrong CAPTCHA code handling
3. **Slot Availability**: Booking unavailable timeslots
4. **Data Persistence**: Slots removed after booking
5. **Multiple Rooms**: A1 vs A2 endpoint differences
6. **Session Management**: CAPTCHA session handling
7. **Error Responses**: Proper Polish error messages
8. **Edge Cases**: Empty dates, malformed requests

## Debugging

### Check Server Logs
The Flask server runs in debug mode and shows all requests/responses.

### API Inspection
- Use `/api/registrations` to see all successful bookings
- Use `/api/timeslots` to see current availability
- Use `/api/reset` to clean slate for testing

### Manual Form Testing
Visit the registration pages directly in browser to test the full UI flow.

## Notes

- Server includes realistic 6-character CAPTCHA generation
- Timeslots are automatically removed after successful booking
- Session management matches original website behavior
- All Polish text and error messages preserved
- CSS styling matches original layout
- PHPSESSID cookies handled correctly for CAPTCHA validation