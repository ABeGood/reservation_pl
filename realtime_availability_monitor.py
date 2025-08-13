"""
Real-time availability monitor for Polish Card appointments.
Monitors https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A1.php every 0.5-3 seconds.
Dynamically extracts datepicker constraints from the web page.
Extends existing ajax2py.py patterns following LEVER framework.
"""

import requests
import time
import json
import re
from datetime import datetime, timedelta
from ajax2py import parse_time_slots
import random

class RealTimeAvailabilityMonitor:
    def __init__(self, page_url="https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A1.php"):
        self.page_url = page_url
        self.base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"
        self.endpoint = "godziny_pokoj_A1.php"
        self.running = False
        self.results = {}
        self.available_dates = []
        self.stats = {
            'checks_performed': 0,
            'slots_found': 0,
            'last_check': None,
            'start_time': None
        }
        
    def extract_datepicker_config(self):
        """Dynamically extract datepicker configuration from the web page."""
        print(f"🔍 Extracting datepicker configuration from {self.page_url}...")
        
        try:
            response = requests.get(self.page_url, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to fetch page: {response.status_code}")
            
            html_content = response.text
            
            # Extract disabled days array
            disabled_days_match = re.search(r'var disabledDays\s*=\s*\[(.*?)\];', html_content, re.DOTALL)
            disabled_days = []
            if disabled_days_match:
                # Extract dates from the array
                dates_str = disabled_days_match.group(1)
                disabled_days = re.findall(r'"(\d{4}-\d{2}-\d{2})"', dates_str)
                print(f"📅 Found {len(disabled_days)} disabled days")
            
            # Extract minDate and maxDate
            min_date_match = re.search(r'minDate:\s*new Date\("(\d{4}/\d{2}/\d{2})"\)', html_content)
            max_date_match = re.search(r'maxDate:\s*new Date\("(\d{4}/\d{2}/\d{2})"\)', html_content)
            
            if not min_date_match or not max_date_match:
                raise Exception("Could not extract minDate/maxDate from page")
            
            # Convert date format from YYYY/MM/DD to YYYY-MM-DD
            min_date_str = min_date_match.group(1).replace('/', '-')
            max_date_str = max_date_match.group(1).replace('/', '-')
            
            min_date = datetime.strptime(min_date_str, "%Y-%m-%d")
            max_date = datetime.strptime(max_date_str, "%Y-%m-%d")
            
            print(f"📅 Date range: {min_date_str} to {max_date_str}")
            print(f"🚫 Disabled days: {len(disabled_days)} dates")
            
            return {
                'min_date': min_date,
                'max_date': max_date,
                'disabled_days': disabled_days
            }
            
        except Exception as e:
            print(f"❌ Error extracting datepicker config: {e}")
            print("Using fallback configuration...")
            # Fallback to reasonable defaults
            return {
                'min_date': datetime.now(),
                'max_date': datetime.now() + timedelta(days=90),
                'disabled_days': []
            }
    
    def get_available_dates(self):
        """Get available dates from today to the last available in datepicker."""
        config = self.extract_datepicker_config()
        available_dates = []
        
        # Start from today, not from datepicker minDate
        today = datetime.now().date()
        current_date = max(config['min_date'].date(), today)  # Use today if it's later than minDate
        current_date = datetime.combine(current_date, datetime.min.time())  # Convert back to datetime
        
        print(f"ℹ️  Checking dates from {current_date.strftime('%Y-%m-%d')} to {config['max_date'].strftime('%Y-%m-%d')}")
        
        while current_date <= config['max_date']:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Only weekdays (Monday=0 to Friday=4)
            if current_date.weekday() < 5 and date_str not in config['disabled_days']:
                available_dates.append(date_str)
            
            current_date += timedelta(days=1)
        
        print(f"ℹ️  Days to check: {', '.join(available_dates[:10])}{'...' if len(available_dates) > 10 else ''}")
        print(f"✅ Found {len(available_dates)} potentially available dates")
        return available_dates
    
    def check_single_date(self, date_str):
        """Check availability for a single date using existing ajax2py pattern."""
        url = f"{self.base_url}{self.endpoint}"
        
        data = {'godzina': date_str}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': self.base_url,
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        try:
            response = requests.post(url, data=data, headers=headers, timeout=10)
            if response.status_code == 200:
                # Reuse existing parse_time_slots function
                slots = parse_time_slots(response.text)
                self.stats['checks_performed'] += 1
                return slots
            else:
                return []
        except Exception as e:
            return []
    
    def check_all_dates_once(self):
        """Single sweep through all available dates."""
        now = datetime.now().strftime('%H:%M:%S')
        print(f"[{now}] Checking {len(self.available_dates)} dates...")
        print(f"ℹ️  Checking dates: {', '.join(self.available_dates[:5])}{'...' if len(self.available_dates) > 5 else ''}")
        
        new_slots_found = False
        for i, date_str in enumerate(self.available_dates):
            if not self.running:
                break
            
            print(f"ℹ️  Checking date {date_str} ({i+1}/{len(self.available_dates)})...")
            
            slots = self.check_single_date(date_str)
            
            # Track changes
            if slots:
                if date_str not in self.results or self.results[date_str] != slots:
                    if date_str not in self.results:
                        print(f"🎉 NEW AVAILABILITY: {date_str} -> {', '.join(slots)}")
                    else:
                        print(f"📝 UPDATED: {date_str} -> {', '.join(slots)}")
                    new_slots_found = True
                    self.stats['slots_found'] += len(slots)
                
                self.results[date_str] = slots
            else:
                # Remove if no longer available
                if date_str in self.results:
                    print(f"❌ REMOVED: {date_str} (no longer available)")
                    del self.results[date_str]
                else:
                    print(f"   No slots available for {date_str}")
            time.sleep(0.2)
        
        self.stats['last_check'] = datetime.now().isoformat()
        return new_slots_found
    
    def start_monitoring(self, max_duration_minutes=None):
        """Start continuous monitoring."""
        print("🚀 Starting real-time availability monitoring...")
        print(f"Monitoring endpoint: {self.base_url}{self.endpoint}")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        self.stats['start_time'] = datetime.now().isoformat()
        
        try:
            start_time = time.time()
            cycle_count = 0
            
            while self.running:
                cycle_count += 1
                cycle_start = time.time()

                self.available_dates = self.get_available_dates()
                
                # Check all dates once
                self.check_all_dates_once()
                
                # Show current status
                self.print_status()
                
                # Check max duration
                if max_duration_minutes:
                    elapsed_minutes = (time.time() - start_time) / 60
                    if elapsed_minutes >= max_duration_minutes:
                        print(f"\n⏰ Stopping after {max_duration_minutes} minutes")
                        break
                
                # Wait before next cycle (additional 2-5 seconds between full cycles)
                cycle_duration = time.time() - cycle_start
                additional_wait = 0.3
                print(f"Cycle {cycle_count} completed in {cycle_duration:.1f}s, waiting {additional_wait:.1f}s before next cycle...\n")
                time.sleep(additional_wait)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        finally:
            self.running = False
            self.save_results()
    
    def print_status(self):
        """Print current monitoring status."""
        now = datetime.now().strftime('%H:%M:%S')
        available_count = len(self.results)
        total_slots = sum(len(slots) for slots in self.results.values())
        
        print(f"[{now}] Status: {available_count} dates with slots, {total_slots} total slots, {self.stats['checks_performed']} checks performed")
        
        if self.results:
            print("Current availability:")
            for date_str, slots in sorted(self.results.items()):
                print(f"  📅 {date_str}: {', '.join(slots)}")
        else:
            print("  ❌ No slots currently available")
    
    def save_results(self):
        """Save current results to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realtime_monitoring_{timestamp}.json"
        
        output = {
            "monitoring_session": {
                "start_time": self.stats['start_time'],
                "end_time": datetime.now().isoformat(),
                "total_checks": self.stats['checks_performed'],
                "page_url": self.page_url,
                "endpoint": f"{self.base_url}{self.endpoint}"
            },
            "final_availability": self.results,
            "statistics": {
                "dates_monitored": len(self.available_dates),
                "dates_with_slots": len(self.results),
                "total_slots_found": sum(len(slots) for slots in self.results.values())
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"📁 Results saved to: {filename}")

def main():
    print("Real-time Polish Card Appointment Monitor")
    print("=========================================")
    
    # Choose monitoring URL
    print("Select monitoring target:")
    print("1. pokoj_A1.php (default)")
    print("2. pokoj_A2.php")
    
    choice = input("Enter choice (1 or 2, default=1): ").strip()
    
    if choice == "2":
        page_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A2.php"
        monitor = RealTimeAvailabilityMonitor(page_url)
        monitor.endpoint = "godziny_pokoj_A2.php"
    else:
        monitor = RealTimeAvailabilityMonitor()
    
    # Ask for monitoring duration
    try:
        duration_input = input("Enter monitoring duration in minutes (or press Enter for indefinite): ").strip()
        max_duration = int(duration_input) if duration_input else None
    except ValueError:
        max_duration = None
    
    monitor.start_monitoring(max_duration_minutes=max_duration)

if __name__ == "__main__":
    main()