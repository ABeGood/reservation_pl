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
from zoneinfo import ZoneInfo
from ajax2py import get_timeslots_for_single_date
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from database import get_pending_registrations, create_reservation_for_registrant
from ajax2py import send_registration_request_with_retry
import base64

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
            'start_time': None,
            'pending_registrants': 0,
            'target_months': [],
            'last_registrant_check': None,
            'successful_registrations': 0,
            'registration_attempts': 0
        }
        self.stats_lock = threading.Lock()
        self.pending_registrants = []
        self.target_months = set()
        self.last_db_check = None
        # self.db_check_interval = 1800  # Check database every n seconds
        self.db_check_interval = 10  # Check database every n seconds
        
    def get_captcha_image(self, session_id=None):
        """Fetch CAPTCHA image from server and return as base64 string."""
        captcha_url = f"{self.base_url}securimage/securimage_show.php"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': self.base_url
        }
        
        cookies = {'PHPSESSID': session_id} if session_id else {}
        
        try:
            response = requests.get(captcha_url, headers=headers, cookies=cookies, timeout=10)
            if response.status_code == 200:
                # Convert image to base64
                captcha_base64 = base64.b64encode(response.content).decode('ascii')
                return captcha_base64, response.cookies.get('PHPSESSID', session_id)
            else:
                print(f"❌ Failed to fetch CAPTCHA: HTTP {response.status_code}")
                return None, None
        except Exception as e:
            print(f"❌ CAPTCHA fetch error: {e}")
            return None, None

    def attempt_auto_registration(self, available_slots):
        """
        Attempt automatic registration for available slots.
        Matches slots to registrants by month and attempts registration.
        
        Args:
            available_slots (list): List of slot dictionaries from get_timeslots()
            
        Returns:
            list: List of successful registration results
        """
        if not available_slots or not self.pending_registrants:
            return []
        
        successful_registrations = []
        
        print(f"🎯 Attempting auto-registration for {len(available_slots)} available slots...")
        
        for slot in available_slots:
            slot_date = slot['date']  # YYYY-MM-DD format
            slot_month = datetime.strptime(slot_date, "%Y-%m-%d").month
            
            # Find first pending registrant for this month (ID order = priority order)
            matching_registrant = None
            for registrant in sorted(self.pending_registrants, key=lambda r: r.id):
                if registrant.desired_month == slot_month:
                    matching_registrant = registrant
                    break
            
            if not matching_registrant:
                print(f"⏭️  No matching registrant for {slot_date} (month {slot_month})")
                continue
                
            print(f"🎯 Attempting registration: {matching_registrant.name} {matching_registrant.surname} → {slot['display_text']}")
            
            try:
                # Prepare registration data
                registrant_data = matching_registrant.to_registration_data()
                timeslot_data = {
                    'date': slot['date'],
                    'timeslot_value': slot['timeslot_value']
                }
                
                # Send registration request with built-in CAPTCHA retry mechanism
                print(f"📤 Sending registration request with automatic CAPTCHA retry...")
                registration_result = send_registration_request_with_retry(
                    base_url=self.base_url,
                    registrant_data=registrant_data,
                    timeslot_data=timeslot_data,
                    max_retries=12
                )
                
                # Process result
                if registration_result.get('success'):
                    # Generate reservation ID and update database
                    import uuid
                    
                    # Use registration code from success data if available, otherwise generate one
                    success_data = registration_result.get('success_data')
                    if success_data and success_data.get('registration_code'):
                        reservation_id = f"{success_data['registration_code']}"
                    else:
                        reservation_id = f"AUTO_{uuid.uuid4().hex[:8].upper()}"
                    
                    success = create_reservation_for_registrant(
                        registrant_id=matching_registrant.id,
                        reservation_id=reservation_id,
                        success_data=success_data
                    )
                    
                    if success:
                        attempt_info = f" (attempt {registration_result.get('attempt', 1)}/{registration_result.get('max_retries', 3) + 1})" if registration_result.get('attempt', 1) > 1 else ""
                        print(f"✅ REGISTRATION SUCCESS: {matching_registrant.name} {matching_registrant.surname}{attempt_info}")
                        
                        if success_data:
                            print(f"   📅 Confirmed: {success_data.get('appointment_date')} {success_data.get('appointment_time')} - {success_data.get('room')}")
                            print(f"   📧 Email: {success_data.get('email')}")
                            print(f"   📞 Phone: {success_data.get('phone')}")
                            print(f"   🆔 Code: {success_data.get('registration_code')}")
                        else:
                            print(f"   📅 Slot: {slot['display_text']}")
                        
                        print(f"   🆔 Reservation: {reservation_id}")
                        
                        successful_registrations.append({
                            'registrant_id': matching_registrant.id,
                            'registrant_name': f"{matching_registrant.name} {matching_registrant.surname}",
                            'reservation_id': reservation_id,
                            'slot_info': slot,
                            'registration_result': registration_result
                        })
                        
                        # Remove from pending list to avoid re-attempts
                        self.pending_registrants = [r for r in self.pending_registrants if r.id != matching_registrant.id]
                        
                        # Update target months after removing registrant
                        self.target_months = set(r.desired_month for r in self.pending_registrants)
                        
                    else:
                        print(f"❌ Database update failed for {matching_registrant.name}")
                        
                else:
                    attempt_info = f" (failed after {registration_result.get('attempt', 1)} attempts)" if registration_result.get('attempt') else ""
                    error_msg = registration_result.get('message') or registration_result.get('error', 'Unknown error')
                    print(f"❌ Registration failed{attempt_info}: {error_msg}")
                    
                # Be nice to server between attempts
                time.sleep(0.2)
                
            except Exception as e:
                print(f"❌ Registration error for {matching_registrant.name}: {e}")
                continue
        
        if successful_registrations:
            print(f"🎉 AUTO-REGISTRATION SUMMARY: {len(successful_registrations)} successful registrations!")
            with self.stats_lock:
                self.stats['successful_registrations'] = self.stats.get('successful_registrations', 0) + len(successful_registrations)
        else:
            print("ℹ️  No successful registrations in this attempt")
            
        return successful_registrations

    def check_pending_registrants(self):
        """Check database for pending registrants and update target months."""
        try:
            self.pending_registrants = get_pending_registrations()
            new_target_months = set(r.desired_month for r in self.pending_registrants)
            
            # Check if target months changed
            if new_target_months != self.target_months:
                print(f"📊 Target months updated: {sorted(new_target_months)} (was: {sorted(self.target_months)})")
                self.target_months = new_target_months
                # Clear available_dates to force recalculation
                self.available_dates = []
            
            with self.stats_lock:
                self.stats['pending_registrants'] = len(self.pending_registrants)
                self.stats['target_months'] = sorted(list(self.target_months))
                self.stats['last_registrant_check'] = datetime.now().isoformat()
            
            self.last_db_check = datetime.now()
            
            print(f"👥 Found {len(self.pending_registrants)} pending registrants for months: {sorted(self.target_months)}")
            
            for registrant in self.pending_registrants:
                print(f"  - {registrant.name} {registrant.surname} (month {registrant.desired_month})")
            
            return len(self.pending_registrants) > 0
            
        except Exception as e:
            print(f"❌ Error checking pending registrants: {e}")
            return len(self.pending_registrants) > 0  # Continue if we had registrants before

    def should_check_database(self):
        """Check if it's time to refresh registrant data from database."""
        if not self.last_db_check:
            return True
        return (datetime.now() - self.last_db_check).seconds >= self.db_check_interval

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
        """Get available dates filtered by registrant desired months."""
        if not self.target_months:
            print("⏸️  No target months - no pending registrants")
            return []
            
        config = self.extract_datepicker_config()
        available_dates = []
        
        # Start from today, not from datepicker minDate
        today = datetime.now().date()
        current_date = max(config['min_date'].date(), today)  # Use today if it's later than minDate
        current_date = datetime.combine(current_date, datetime.min.time())  # Convert back to datetime
        
        print(f"ℹ️  Checking dates from {current_date.strftime('%Y-%m-%d')} to {config['max_date'].strftime('%Y-%m-%d')}")
        print(f"🎯 Filtering for target months: {sorted(self.target_months)}")
        
        while current_date <= config['max_date']:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Only weekdays (Monday=0 to Friday=4) in target months
            if (current_date.weekday() < 5 and 
                date_str not in config['disabled_days'] and
                current_date.month in self.target_months):
                available_dates.append(date_str)
            
            current_date += timedelta(days=1)
        
        print(f"ℹ️  Days to check: {', '.join(available_dates[:10])}{'...' if len(available_dates) > 10 else ''}")
        print(f"✅ Found {len(available_dates)} potentially available dates in target months")
        return available_dates
    
    def get_timeslots(self):
        """Single sweep through all available dates using parallel processing.
        Returns structured timeslot data ready for registration process."""
        now = datetime.now().strftime('%H:%M:%S')
        
        # Skip server calls if no available dates
        if not self.available_dates:
            print(f"[{now}] ⏸️  No dates to check - skipping server calls")
            return {
                'slots_found': False,
                'total_available_slots': 0,
                'registration_data': [],
                'raw_results': {},
                'stats': {
                    'checks_performed': self.stats['checks_performed'],
                    'dates_checked': 0,
                    'last_check': datetime.now().isoformat()
                }
            }
        
        print(f"[{now}] Checking {len(self.available_dates)} dates in parallel...")
        print(f"ℹ️  Checking dates: {', '.join(self.available_dates[:5])}{'...' if len(self.available_dates) > 5 else ''}")
        
        new_slots_found = False
        max_workers = min(8, len(self.available_dates))  # Use 8 workers max, or fewer if less dates
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all date checks
            future_to_date = {
                executor.submit(get_timeslots_for_single_date, date_str, self.base_url, self.endpoint): date_str 
                for date_str in self.available_dates
            }
            
            completed_count = 0
            total_dates = len(self.available_dates)
            
            # Process results as they complete
            for future in as_completed(future_to_date):
                if not self.running:
                    break
                
                try:
                    date_str, slots = future.result()
                    completed_count += 1
                    self.stats['checks_performed'] += 1

                    # Filter out past timeslots for today (Poland timezone)
                    current_datetime = datetime.now(ZoneInfo("Europe/Warsaw"))
                    if date_str == current_datetime.strftime("%Y-%m-%d"):
                        # Add 3-hour buffer to current time
                        buffer_datetime = current_datetime + timedelta(hours=3)   # AG: Time buffer
                        buffer_time = buffer_datetime.strftime("%H:%M")
                        slots = [slot for slot in slots if slot > buffer_time]
                    
                    print(f"ℹ️  Completed {date_str} ({completed_count}/{total_dates}) - {len(slots)} slots")
                    
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
                        # Don't print "no slots" for every date to reduce noise
                
                except Exception as e:
                    print(f"❌ Error checking {future_to_date[future]}: {e}")
        
        self.stats['last_check'] = datetime.now().isoformat()
        print(f"✅ Parallel check completed: {completed_count}/{total_dates} dates processed")
        
        # Return structured data ready for registration
        registration_ready_slots = []
        for date_str, slots in self.results.items():
            for slot in slots:
                # Extract room identifier from endpoint (A1 or A2)
                room_id = "A1" if "A1" in self.endpoint else "A2"
                
                # Format: Room + time (e.g., "A209:00")
                timeslot_value = f"{room_id}{slot}"
                
                registration_ready_slots.append({
                    'date': date_str,           # Format: YYYY-MM-DD (for datepicker field)
                    'time': slot,              # Format: HH:MM
                    'timeslot_value': timeslot_value,  # Format: A2HH:MM (for godzina radio button)
                    'room': room_id,           # A1 or A2
                    'display_text': f"{date_str} at {slot}",
                    'radio_button': {
                        'id': timeslot_value,
                        'name': 'godzina',
                        'value': timeslot_value
                    }
                })
        
        return {
            'slots_found': new_slots_found,
            'total_available_slots': len(registration_ready_slots),
            'registration_data': registration_ready_slots,
            'raw_results': self.results,
            'stats': {
                'checks_performed': self.stats['checks_performed'],
                'dates_checked': completed_count,
                'last_check': self.stats['last_check']
            }
        }
    
    def start_monitoring(self, max_duration_minutes=None):
        """Start continuous monitoring with database-aware smart scheduling."""
        print("🚀 Starting smart real-time availability monitoring with AUTO-REGISTRATION...")
        print(f"Monitoring endpoint: {self.base_url}{self.endpoint}")
        print("📊 Database integration: ✅ Enabled")
        print("🎯 Smart scheduling: Only monitors months with pending registrants")
        print("⏸️  Auto-pause: Stops server calls when no pending registrants")
        print("🤖 Auto-registration: ✅ Enabled - will attempt to register users automatically")
        print("🔍 CAPTCHA solving: ✅ Enabled via apitruecaptcha.org")
        print("Press Ctrl+C to stop\n")
        
        self.running = True
        self.stats['start_time'] = datetime.now().isoformat()
        
        try:
            start_time = time.time()
            cycle_count = 0
            wait_cycles = 0
            
            while self.running:
                cycle_count += 1
                cycle_start = time.time()

                # Check database for new/removed registrants periodically
                if self.should_check_database():
                    has_registrants = self.check_pending_registrants()
                    if not has_registrants:
                        wait_cycles += 1
                        if wait_cycles == 1:
                            print("⏸️  No pending registrants - entering standby mode")
                        print(f"💤 Standby cycle {wait_cycles} - checking for new registrants in {self.db_check_interval}s...")
                        time.sleep(self.db_check_interval+10)  # AG: Not very nice!
                        continue
                    elif wait_cycles > 0:
                        print("🎉 Found pending registrants - resuming active monitoring!")
                        wait_cycles = 0

                # Get available dates (filtered by target months)
                self.available_dates = self.get_available_dates()
                
                # Check dates (will skip server calls if no dates)
                result = self.get_timeslots()
                
                # Attempt auto-registration if slots are available
                if result['total_available_slots'] > 0:
                    print(f"🔥 SLOTS DETECTED! Attempting auto-registration...")
                    successful_registrations = self.attempt_auto_registration(result['registration_data'])
                    
                    if successful_registrations:
                        # Refresh registrant list after successful registrations
                        print("🔄 Refreshing pending registrants after successful registrations...")
                        self.check_pending_registrants()
                        
                        # If no more pending registrants, we can reduce frequency
                        if not self.pending_registrants:
                            print("🎉 All registrants have been registered! Switching to standby mode...")
                
                # Show current status
                self.print_status()
                
                # Check max duration
                if max_duration_minutes:
                    elapsed_minutes = (time.time() - start_time) / 60
                    if elapsed_minutes >= max_duration_minutes:
                        print(f"\n⏰ Stopping after {max_duration_minutes} minutes")
                        break
                
                # Adaptive wait time based on results
                cycle_duration = time.time() - cycle_start
                if result['total_available_slots'] > 0:
                    additional_wait = 0.3  # Quick check when slots found
                    print(f"🔥 Slots available! Quick cycle {cycle_count} completed in {cycle_duration:.1f}s, waiting {additional_wait:.1f}s...")
                else:
                    additional_wait = 0.3  # Longer wait when no slots
                    print(f"Cycle {cycle_count} completed in {cycle_duration:.1f}s, waiting {additional_wait:.1f}s before next cycle...")
                
                time.sleep(additional_wait)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        finally:
            self.running = False
            self.save_results()
    
    def print_status(self):
        """Print current monitoring status with registrant information."""
        now = datetime.now().strftime('%H:%M:%S')
        available_count = len(self.results)
        total_slots = sum(len(slots) for slots in self.results.values())
        pending_count = len(self.pending_registrants)
        
        successful_regs = self.stats.get('successful_registrations', 0)
        print(f"[{now}] Status: {available_count} dates with slots, {total_slots} total slots, {pending_count} pending registrants")
        print(f"🎯 Target months: {sorted(self.target_months) if self.target_months else 'None'} | Server checks: {self.stats['checks_performed']} | ✅ Registered: {successful_regs}")
        
        if self.results:
            print("Current availability:")
            for date_str, slots in sorted(self.results.items()):
                month = datetime.strptime(date_str, "%Y-%m-%d").month
                matching_registrants = [r for r in self.pending_registrants if r.desired_month == month]
                print(f"  📅 {date_str}: {', '.join(slots)} → {len(matching_registrants)} registrants interested")
        else:
            if self.target_months:
                print("  ❌ No slots currently available in target months")
            else:
                print("  ⏸️  No target months - no pending registrants")
    
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