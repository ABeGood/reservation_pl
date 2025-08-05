import requests
from datetime import datetime, timedelta
import time

def get_available_times(date, base_url):
    """Replicate the AJAX call to get available appointment times"""
    url = f"{base_url}godziny_pokoj_A2.php"
    
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

def check_multiple_days(start_date, end_date, base_url):
    """Check availability for multiple days"""
    
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    current = start
    results = {}
    
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        
        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() < 5:  # Monday=0 to Friday=4
            print(f"Checking {date_str}...")
            result = get_available_times(date_str, base_url)
            results[date_str] = result
            
            # Be nice to the server - wait between requests
            time.sleep(1)
        
        current += timedelta(days=1)
    
    return results

# Quick availability checker
def find_available_days(start_date, end_date, base_url):
    """Find days with available slots"""
    results = check_multiple_days(start_date, end_date, base_url)
    available_days = []
    
    for date, result in results.items():
        # Customize this condition based on actual response format
        if result.strip() and "brak" not in result.lower():
            available_days.append(date)
    
    return available_days

# Usage examples:
base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"

available = find_available_days("2025-08-05", "2025-09-30", base_url)
print(f"\nAvailable days: {available}")

# # Check specific dates
# dates_to_check = ["2025-06-16", "2025-06-17", "2025-06-18"]
# for date in dates_to_check:
#     result = get_available_times(date, base_url)
#     print(f"{date}: {result[:100]}...")  # First 100 chars

# print("\n" + "="*50 + "\n")

# # Check date range
# results = check_multiple_days("2025-06-16", "2025-06-30", base_url)
# for date, result in results.items():
#     if "available" in result.lower() or result.strip():  # Only show days with content
#         print(f"{date}: {result[:100]}...")