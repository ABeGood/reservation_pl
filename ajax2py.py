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

def send_registration_request(base_url:str, registrant_data:dict, capcha:str):
    url = f"{base_url}/send.php"

    cookies = {
        "PHPSESSID": "9c61b45f8b29a0e306d5c39d2fea62a7"
    }

    payload = {
        "imie": registrant_data['name'],
        "nazwisko": registrant_data['surname'],
        "obywatelstwo": registrant_data['nationality'],
        "email": registrant_data['email'],
        "telefon": registrant_data['phone'],
        "rodzaj_wizyty": registrant_data['registration_type'],
        "datepicker": # TODO,
        "godzina": # TODO,
        "captcha_code": capcha
    }

    r = requests.post(url, 
                    cookies=cookies,
                    data=payload)
    print(r.status_code, r.text)


# Usage examples:
base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"

# # Check specific dates
# dates_to_check = ["2025-06-16", "2025-06-17", "2025-06-18"]
# for date in dates_to_check:
#     result = get_available_times(date, base_url)
#     print(f"{date}: {result[:100]}...")  # First 100 chars

# print("\n" + "="*50 + "\n")

available = check_multiple_days_with_times("2025-08-05", "2025-11-30", base_url)
print(f"\nAvailable days: {available}")

with open('days.json', 'w', encoding='utf-8') as f:
    json.dump(available, f, ensure_ascii=False, indent=2)