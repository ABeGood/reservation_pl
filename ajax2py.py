import requests
from datetime import datetime, timedelta
import time
import re
import json

def get_available_times(date, base_url):
    """Replicate the AJAX call to get available appointment times"""
    url = f"{base_url}godziny_pokoj_A1.php"
    
    data = {'godzina': date}
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': base_url,
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    try:
        response = requests.post(url, data=data, headers=headers)
        if response.status_code == 200:
            return response.text
        else:
            return f"Error: {response.status_code}"
    except requests.RequestException as e:
        return f"Request failed: {e}"

def parse_time_slots(html_response):
    """Extract available time slots from HTML response"""
    if "Brak wolnych godzin" in html_response:
        return []
    
    # Extract time slots from radio inputs
    # Pattern: <label for="A209:00">09:00</label>
    time_pattern = r'<label for="[^"]*">(\d{2}:\d{2})</label>'
    times = re.findall(time_pattern, html_response)
    
    return times

def get_times_for_date(date, base_url):
    """Get parsed time slots for a specific date"""
    html_response = get_available_times(date, base_url)
    times = parse_time_slots(html_response)
    return times

def check_multiple_days_with_times(start_date, end_date, base_url):
    """Check availability and get time slots for multiple days"""
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    current = start
    results = {}
    
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        
        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() < 5:  # Monday=0 to Friday=4
            print(f"Checking {date_str}...")
            times = get_times_for_date(date_str, base_url)
            results[date_str] = times
            
            # Be nice to the server - wait between requests
            time.sleep(1)
        
        current += timedelta(days=1)
    
    return results

def send_registration_request(base_url: str, registrant_data: dict, timeslot_data: dict, captcha_code: str, session_id: str = None):
    """
    Send registration request to the Polish Card appointment system.
    
    Args:
        base_url (str): Base URL of the appointment system
        registrant_data (dict): Personal information with keys:
            - name (str): First name (max 15 chars)
            - surname (str): Last name (max 20 chars)
            - citizenship (str): One of ['Białoruś', 'Rosja', 'Ukraina', 'status bezpaństwowca']
            - email (str): Email address
            - phone (str): Phone number (digits only)
            - application_type (str): One of ['osoba dorosła', 'osoba dorosła i małoletnie dzieci', 'małoletni']
        timeslot_data (dict): Appointment slot with keys:
            - date (str): Date in YYYY-MM-DD format
            - timeslot_value (str): Full timeslot value (e.g., 'A209:00')
        captcha_code (str): Solved CAPTCHA code (max 6 chars)
        session_id (str, optional): PHPSESSID cookie value. If None, will attempt to get one.
    
    Returns:
        dict: Response with success status and details
    """
    url = f"{base_url}send.php" if base_url.endswith('/') else f"{base_url}/send.php"
    
    # Session management: Get session if not provided
    if not session_id:
        session_id = get_session_id(base_url)
    
    cookies = {
        "PHPSESSID": session_id
    } if session_id else {}

    # Complete form payload matching the HTML form structure
    payload = {
        "imie": registrant_data['name'],
        "nazwisko": registrant_data['surname'], 
        "obywatelstwo": registrant_data['citizenship'],
        "email": registrant_data['email'],
        "telefon": registrant_data['phone'],
        "rodzaj_wizyty": registrant_data['application_type'],
        "datepicker": timeslot_data['date'],           # Format: YYYY-MM-DD
        "godzina": timeslot_data['timeslot_value'],    # Format: A1HH:MM or A2HH:MM
        "captcha_code": captcha_code
    }
    
    # Headers to mimic browser form submission
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
    
    try:
        response = requests.post(url, 
                               data=payload,
                               cookies=cookies,
                               headers=headers,
                               timeout=30,
                               allow_redirects=True)
        
        # Parse response
        result = {
            'success': False,
            'status_code': response.status_code,
            'response_text': response.text,
            'url': response.url,
            'cookies': dict(response.cookies),
            'payload_sent': payload
        }
        
        # Check for success indicators in response
        if response.status_code == 200:
            response_text = response.text.lower()
            if any(success_phrase in response_text for success_phrase in [
                'rezerwacja została', 'potwierdzenie', 'sukces', 'zarezerwowano'
            ]):
                result['success'] = True
                result['message'] = 'Registration appears successful'
            elif any(error_phrase in response_text for error_phrase in [
                'błąd', 'error', 'nieprawidłowy', 'captcha'
            ]):
                result['message'] = 'Registration failed - check response for details'
            else:
                result['message'] = 'Registration status unclear - check response manually'
        else:
            result['message'] = f'HTTP error: {response.status_code}'
            
        return result
        
    except requests.RequestException as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Request failed',
            'payload_sent': payload
        }


def get_session_id(base_url: str):
    """
    Get a valid PHPSESSID by visiting the CAPTCHA endpoint.
    
    Args:
        base_url (str): Base URL of the appointment system
        
    Returns:
        str: PHPSESSID value or None if failed
    """
    captcha_url = f"{base_url}securimage/securimage_show.php" if not base_url.endswith('/') else f"{base_url}securimage/securimage_show.php"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(captcha_url, headers=headers, timeout=10)
        if response.status_code == 200 and 'PHPSESSID' in response.cookies:
            return response.cookies['PHPSESSID']
    except requests.RequestException:
        pass
    
    return None


# Usage examples:
# base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"

# # Check specific dates
# dates_to_check = ["2025-06-16", "2025-06-17", "2025-06-18"]
# for date in dates_to_check:
#     result = get_available_times(date, base_url)
#     print(f"{date}: {result[:100]}...")  # First 100 chars

# print("\n" + "="*50 + "\n")

# available = check_multiple_days_with_times("2025-08-05", "2025-11-30", base_url)
# print(f"\nAvailable days: {available}")

# with open('days.json', 'w', encoding='utf-8') as f:
#     json.dump(available, f, ensure_ascii=False, indent=2)