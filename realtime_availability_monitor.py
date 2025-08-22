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
from monitor_events_manager import (
    get_event_emitter,
    emit_error,
    emit_slot_found,
    emit_registration_success,
    emit_registration_failed,
    emit_status_update,
    emit_datepicker_change
)
import base64
from logging_config import get_logger

logger = get_logger(__name__)

class RealTimeAvailabilityMonitor:
    def __init__(self, page_url="https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A1.php", use_mock_server=False):
        if use_mock_server:
            self.page_url = page_url.replace("https://olsztyn.uw.gov.pl/wizytakartapolaka/", "http://localhost:5000/")
            self.base_url = "http://localhost:5000/"
            self.endpoint = "godziny_pokoj_A1.php"  # Mock server uses same endpoint names
            # Update endpoint if A2 is in the page URL
            if "A2" in page_url:
                self.endpoint = "godziny_pokoj_A2.php"
        else:
            self.page_url = page_url
            self.base_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/"
            self.endpoint = "godziny_pokoj_A1.php"
            # Update endpoint if A2 is in the page URL
            if "A2" in page_url:
                self.endpoint = "godziny_pokoj_A2.php"
        self.stop_event = threading.Event()
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
            'registration_attempts': 0,
            'last_status_log': None,
            'cycle_duration': 0
        }
        self.datepicker_config = None
        self.stats_lock = threading.Lock()
        self.pending_registrants = []
        self.target_months = set()
        self.last_db_check = None
        self.db_check_interval = 1800  # Check database every n seconds
        
        # Event emitter for Telegram notifications
        self.event_emitter = get_event_emitter()
    
    def get_current_stats(self):
        """Get current statistics (thread-safe)."""
        with self.stats_lock:
            return self.stats.copy()
    
    def refresh_pending_registrants(self):
        """Refresh pending registrants from database."""
        try:
            self.pending_registrants = get_pending_registrations()
            self.target_months = {r.desired_month for r in self.pending_registrants}
            
            with self.stats_lock:
                self.stats['pending_registrants'] = len(self.pending_registrants)
                self.stats['target_months'] = list(self.target_months)
                self.stats['last_registrant_check'] = datetime.now().isoformat()
            
            logger.info(f"🗄️ Database refresh: {len(self.pending_registrants)} pending registrants for months {list(self.target_months)}")
            return True
        except Exception as e:
            error_msg = f"Failed to refresh database: {str(e)}"
            logger.error(f"❌ {error_msg}")
            emit_error(error_msg, {'exception': str(e)})
            return False
        
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
                logger.error(f"❌ Failed to fetch CAPTCHA: HTTP {response.status_code}")
                return None, None
        except Exception as e:
            logger.error(f"❌ CAPTCHA fetch error: {e}")
            return None, None

    def distribute_registrants_to_slots(self, available_slots):
        """
        Distribute pending registrants across available timeslots based on priority and desired months.
        Lower registrant ID = higher priority.
        
        Args:
            available_slots (list): List of slot dictionaries from get_timeslots()
            
        Returns:
            list: List of (registrant, slot) assignment tuples
        """
        if not available_slots or not self.pending_registrants:
            return []
        
        # Group available slots by month
        slots_by_month = {}
        for slot in available_slots:
            slot_month = datetime.strptime(slot['date'], "%Y-%m-%d").month
            if slot_month not in slots_by_month:
                slots_by_month[slot_month] = []
            slots_by_month[slot_month].append(slot)
        
        # Group registrants by desired month, sorted by ID (lower ID = higher priority)
        registrants_by_month = {}
        for registrant in sorted(self.pending_registrants, key=lambda r: r.id):
            month = registrant.desired_month
            if month not in registrants_by_month:
                registrants_by_month[month] = []
            registrants_by_month[month].append(registrant)
        
        # Create registrant-slot assignments
        assignments = []
        for month in slots_by_month:
            if month in registrants_by_month:
                slots = slots_by_month[month]
                registrants = registrants_by_month[month]
                
                # Sort slots by date and time to ensure earliest slots go to highest priority registrants
                slots_sorted = sorted(slots, key=lambda s: (s['date'], s['time']))
                
                logger.info(f"📅 Month {month}: {len(slots)} slots, {len(registrants)} registrants")
                
                # Distribute slots to registrants based on priority
                # If more slots than registrants, highest priority registrants get first choice
                # If more registrants than slots, only highest priority registrants get slots
                for i, slot in enumerate(slots_sorted):
                    if i < len(registrants):
                        registrant = registrants[i]
                        assignments.append((registrant, slot))
                        logger.info(f"  🎯 Assigned: {registrant.name} {registrant.surname} (ID:{registrant.id}) → {slot['display_text']}")
        
        logger.info(f"📋 Total assignments: {len(assignments)}")
        return assignments

    def attempt_single_registration(self, registrant, slot):
        """
        Attempt registration for a single registrant-slot pair.
        Used for parallel registration processing.
        
        Args:
            registrant: Registrant object with .to_registration_data() method
            slot: Slot dictionary with 'date' and 'timeslot_value' keys
            
        Returns:
            dict: Registration attempt result with registrant and slot info
        """
        try:
            logger.info(f"🎯 Starting registration: {registrant.name} {registrant.surname} → {slot['display_text']}")
            
            # Prepare registration data
            registrant_data = registrant.to_registration_data()
            timeslot_data = {
                'date': slot['date'],
                'timeslot_value': slot['timeslot_value']
            }
            
            # Send registration request with built-in CAPTCHA retry mechanism
            registration_result = send_registration_request_with_retry(
                base_url=self.base_url,
                registrant_data=registrant_data,
                timeslot_data=timeslot_data,
                max_retries=12
            )
            
            return {
                'registrant': registrant,
                'slot': slot,
                'registrant_data': registrant_data,
                'result': registration_result,
                'success': registration_result.get('success', False)
            }
            
        except Exception as e:
            error_msg = f"Registration attempt failed for {registrant.name}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return {
                'registrant': registrant,
                'slot': slot,
                'registrant_data': registrant.to_registration_data() if hasattr(registrant, 'to_registration_data') else {},
                'result': {'success': False, 'error': error_msg},
                'success': False
            }

    def attempt_auto_registration(self, available_slots):
        """
        Attempt automatic registration using parallel processing and smart distribution.
        Distributes registrants across slots by priority and runs registration attempts in parallel.
        
        Args:
            available_slots (list): List of slot dictionaries from get_timeslots()
            
        Returns:
            list: List of successful registration results
        """
        if not available_slots or not self.pending_registrants:
            return []
        
        # Step 1: Distribute registrants to slots based on priority and desired months
        assignments = self.distribute_registrants_to_slots(available_slots)
        
        if not assignments:
            logger.info("⏭️  No matching registrant-slot assignments found")
            return []
        
        logger.info(f"🚀 Starting PARALLEL registration for {len(assignments)} assignments...")
        
        successful_registrations = []
        max_workers = min(8, len(assignments))  # Use up to 8 parallel workers
        
        # Step 2: Execute registration attempts in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all registration attempts
            future_to_assignment = {
                executor.submit(self.attempt_single_registration, registrant, slot): (registrant, slot)
                for registrant, slot in assignments
            }
            
            completed_count = 0
            total_assignments = len(assignments)
            
            # Process results as they complete
            for future in as_completed(future_to_assignment):
                try:
                    attempt_result = future.result()
                    completed_count += 1
                    
                    registrant = attempt_result['registrant']
                    slot = attempt_result['slot']
                    registration_result = attempt_result['result']
                    
                    logger.info(f"📋 Completed {completed_count}/{total_assignments}: {registrant.name} {registrant.surname}")
                    
                    # Process successful registration
                    if attempt_result['success']:
                        # Generate reservation ID and update database
                        import uuid
                        
                        success_data = registration_result.get('success_data')
                        if success_data and success_data.get('registration_code'):
                            reservation_id = f"{success_data['registration_code']}"
                        else:
                            reservation_id = f"AUTO_{uuid.uuid4().hex[:8].upper()}"
                        
                        success = create_reservation_for_registrant(
                            registrant_id=registrant.id,
                            reservation_id=reservation_id,
                            success_data=success_data
                        )
                        
                        if success:
                            # Emit registration success event
                            emit_registration_success(
                                registrant_data=attempt_result['registrant_data'],
                                slot_data=slot
                            )
                            
                            attempt_info = f" (attempt {registration_result.get('attempt', 1)}/{registration_result.get('max_retries', 12) + 1})" if registration_result.get('attempt', 1) > 1 else ""
                            logger.info(f"✅ REGISTRATION SUCCESS: {registrant.name} {registrant.surname}{attempt_info}")
                            
                            if success_data:
                                logger.info(f"   📅 Confirmed: {success_data.get('appointment_date')} {success_data.get('appointment_time')} - {success_data.get('room')}")
                                logger.info(f"   📧 Email: {success_data.get('email')}")
                                logger.info(f"   📞 Phone: {success_data.get('phone')}")
                                logger.info(f"   🆔 Code: {success_data.get('registration_code')}")
                            else:
                                logger.info(f"   📅 Slot: {slot['display_text']}")
                            
                            logger.info(f"   🆔 Reservation: {reservation_id}")
                            
                            successful_registrations.append({
                                'registrant_id': registrant.id,
                                'registrant_name': f"{registrant.name} {registrant.surname}",
                                'reservation_id': reservation_id,
                                'slot_info': slot,
                                'registration_result': registration_result
                            })
                            
                            # Remove from pending list to avoid re-attempts
                            self.pending_registrants = [r for r in self.pending_registrants if r.id != registrant.id]
                            
                        else:
                            error_msg = f"Database update failed for {registrant.name}"
                            logger.error(f"❌ {error_msg}")
                            emit_registration_failed(
                                registrant_data=attempt_result['registrant_data'],
                                slot_data=slot,
                                error=error_msg
                            )
                    
                    else:
                        # Registration failed
                        attempt_info = f" (failed after {registration_result.get('attempt', 1)} attempts)" if registration_result.get('attempt') else ""
                        error_msg = registration_result.get('message') or registration_result.get('error', 'Unknown error')
                        full_error_msg = f"Registration failed{attempt_info}: {error_msg}"
                        logger.error(f"❌ {full_error_msg}")
                        
                        emit_registration_failed(
                            registrant_data=attempt_result['registrant_data'],
                            slot_data=slot,
                            error=full_error_msg
                        )
                
                except Exception as e:
                    registrant, slot = future_to_assignment[future]
                    error_msg = f"Parallel registration error for {registrant.name}: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    emit_registration_failed(
                        registrant_data=registrant.to_registration_data(),
                        slot_data=slot,
                        error=error_msg
                    )
        
        # Step 3: Update target months after successful registrations
        if successful_registrations:
            self.target_months = set(r.desired_month for r in self.pending_registrants)
            
            logger.info(f"🎉 PARALLEL REGISTRATION SUMMARY: {len(successful_registrations)} successful registrations!")
            with self.stats_lock:
                self.stats['successful_registrations'] = self.stats.get('successful_registrations', 0) + len(successful_registrations)
        else:
            logger.info("ℹ️  No successful registrations in parallel attempt")
            
        return successful_registrations

    def check_pending_registrants(self):
        """Check database for pending registrants and update target months."""
        try:
            self.pending_registrants = get_pending_registrations()
            new_target_months = set(r.desired_month for r in self.pending_registrants)
            
            # Check if target months changed
            if new_target_months != self.target_months:
                logger.info(f"📊 Target months updated: {sorted(new_target_months)} (was: {sorted(self.target_months)})")
                self.target_months = new_target_months
                # Clear available_dates to force recalculation
                self.available_dates = []
            
            with self.stats_lock:
                self.stats['pending_registrants'] = len(self.pending_registrants)
                self.stats['target_months'] = sorted(list(self.target_months))
                self.stats['last_registrant_check'] = datetime.now().isoformat()
            
            self.last_db_check = datetime.now()
            
            logger.info(f"👥 Found {len(self.pending_registrants)} pending registrants for months: {sorted(self.target_months)}")
            
            for registrant in self.pending_registrants:
                logger.info(f"  - {registrant.name} {registrant.surname} (month {registrant.desired_month})")
            
            return len(self.pending_registrants) > 0
            
        except Exception as e:
            logger.error(f"❌ Error checking pending registrants: {e}")
            return len(self.pending_registrants) > 0  # Continue if we had registrants before

    def should_check_database(self):
        """Check if it's time to refresh registrant data from database."""
        if not self.last_db_check:
            return True
        return (datetime.now() - self.last_db_check).seconds >= self.db_check_interval

    def extract_datepicker_config(self, verbose=False):
        """Dynamically extract datepicker configuration from the web page."""
        if verbose:
            logger.info(f"🔍 Extracting datepicker configuration from {self.page_url}...")
        
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
                if verbose:
                    logger.info(f"📅 Found {len(disabled_days)} disabled days")
            
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
            
            if verbose:
                logger.info(f"📅 Date range: {min_date_str} to {max_date_str}")
                logger.info(f"🚫 Disabled days: {len(disabled_days)} dates")
            
            return {
                'min_date': min_date,
                'max_date': max_date,
                'disabled_days': disabled_days
            }
            
        except Exception as e:
            logger.error(f"❌ Error extracting datepicker config: {e}")
            if verbose:
                logger.info("Using fallback configuration...")
            # Fallback to reasonable defaults
            return {
                'min_date': datetime.now(),
                'max_date': datetime.now() + timedelta(days=90),
                'disabled_days': []
            }
    
    def _detect_datepicker_changes(self, old_datepicker, new_datepicker):
        """Detect changes between datepicker configurations."""
        changes = []
        
        # Check date range changes
        if old_datepicker['min_date'] != new_datepicker['min_date']:
            changes.append(f"min_date: {old_datepicker['min_date'].strftime('%Y-%m-%d')} → {new_datepicker['min_date'].strftime('%Y-%m-%d')}")
        
        if old_datepicker['max_date'] != new_datepicker['max_date']:
            changes.append(f"max_date: {old_datepicker['max_date'].strftime('%Y-%m-%d')} → {new_datepicker['max_date'].strftime('%Y-%m-%d')}")
        
        # Check disabled days changes
        old_disabled = set(old_datepicker['disabled_days'])
        new_disabled = set(new_datepicker['disabled_days'])
        
        newly_disabled = new_disabled - old_disabled
        newly_enabled = old_disabled - new_disabled
        
        if newly_disabled:
            changes.append(f"newly_disabled: {sorted(list(newly_disabled))}")
        
        if newly_enabled:
            changes.append(f"newly_enabled: {sorted(list(newly_enabled))}")
        
        return changes
    
    def get_available_dates(self, verbose=False):
        """Get available dates filtered by registrant desired months."""
        if not self.target_months:
            if verbose:
                logger.info("⏸️  No target months - no pending registrants")
            return []
            
        new_datepicker_config = self.extract_datepicker_config(verbose=verbose)
        # Detect changes
        if self.datepicker_config is not None:
            changes = self._detect_datepicker_changes(self.datepicker_config, new_datepicker_config)
            if changes:
                logger.info(f"🔄 Datepicker config changed: {changes}")
                emit_datepicker_change(
                    old_config=self.datepicker_config,
                    new_config=new_datepicker_config,
                    changes=changes
                )
        self.datepicker_config = new_datepicker_config

        available_dates = []
        
        # Start from today, not from datepicker minDate
        today = datetime.now().date()
        current_date = max(self.datepicker_config['min_date'].date(), today)  # Use today if it's later than minDate
        current_date = datetime.combine(current_date, datetime.min.time())  # Convert back to datetime
        
        if verbose:
            logger.info(f"ℹ️  Checking dates from {current_date.strftime('%Y-%m-%d')} to {self.datepicker_config['max_date'].strftime('%Y-%m-%d')}")
            logger.info(f"🎯 Filtering for target months: {sorted(self.target_months)}")
        
        while current_date <= self.datepicker_config['max_date']:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Only weekdays (Monday=0 to Friday=4) in target months
            if (current_date.weekday() < 5 and 
                date_str not in self.datepicker_config['disabled_days'] and
                current_date.month in self.target_months):
                available_dates.append(date_str)
            
            current_date += timedelta(days=1)
        
        if verbose:
            logger.info(f"ℹ️  Days to check: {', '.join(available_dates[:10])}{'...' if len(available_dates) > 10 else ''}")
            logger.info(f"✅ Found {len(available_dates)} potentially available dates in target months")
        return available_dates
    
    def get_timeslots(self, verbose=False):
        """Single sweep through all available dates using parallel processing.
        Returns structured timeslot data ready for registration process."""
        now = datetime.now().strftime('%H:%M:%S')
        
        # Clear previous results to ensure we only return current cycle data
        self.results = {}
        
        # Skip server calls if no available dates
        if not self.available_dates:
            if verbose:
                logger.info(f"[{now}] ⏸️  No dates to check - skipping server calls")
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
        
        if verbose:
            logger.info(f"[{now}] Checking {len(self.available_dates)} dates in parallel...")
            logger.info(f"ℹ️  Checking dates: {', '.join(self.available_dates[:5])}{'...' if len(self.available_dates) > 5 else ''}")
        
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
                if self.stop_event.is_set():
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
                    
                    if verbose:
                        logger.info(f"ℹ️  Completed {date_str} ({completed_count}/{total_dates}) - {len(slots)} slots")
                    
                    # Track changes
                    if slots:
                        if date_str not in self.results or self.results[date_str] != slots:
                            if date_str not in self.results:
                                logger.info(f"🎉 NEW AVAILABILITY: {date_str} -> {', '.join(slots)}")
                            else:
                                logger.info(f"📝 UPDATED: {date_str} -> {', '.join(slots)}")
                            new_slots_found = True
                            self.stats['slots_found'] += len(slots)
                        
                        self.results[date_str] = slots
                    else:
                        # Remove if no longer available
                        if date_str in self.results:
                            logger.info(f"❌ REMOVED: {date_str} (no longer available)")
                            del self.results[date_str]
                        # Don't print "no slots" for every date to reduce noise
                
                except Exception as e:
                    logger.error(f"❌ Error checking {future_to_date[future]}: {e}")
        
        self.stats['last_check'] = datetime.now().isoformat()
        if verbose:
            logger.info(f"✅ Parallel check completed: {completed_count}/{total_dates} dates processed")
        
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
    
    def start_monitoring(self, max_duration_minutes=None, check_interval:float=0.5, auto_registration:bool=True):
        """Start continuous monitoring with database-aware smart scheduling."""
        logger.info("🚀 Starting smart real-time availability monitoring with AUTO-REGISTRATION...")
        logger.info(f"Monitoring endpoint: {self.base_url}{self.endpoint}")
        logger.info("📊 Database integration: ✅ Enabled")
        logger.info("🎯 Smart scheduling: Only monitors months with pending registrants")
        logger.info("⏸️  Auto-pause: Stops server calls when no pending registrants")
        logger.info("🤖 Auto-registration: ✅ Enabled - will attempt to register users automatically")
        logger.info("🔍 CAPTCHA solving: ✅ Enabled via apitruecaptcha.org")
        logger.info("Press Ctrl+C to stop\n")
        
        self.stop_event.clear()
        self.stats['start_time'] = datetime.now().isoformat()
        
        try:
            start_time = time.time()
            cycle_count = 0
            wait_cycles = 0
            
            while not self.stop_event.is_set():
                cycle_count += 1
                cycle_start = time.time()

                try:
                    # Check database for new/removed registrants periodically
                    if self.should_check_database():
                        has_registrants = self.check_pending_registrants()
                        if not has_registrants:
                            wait_cycles += 1
                            if wait_cycles == 1:
                                logger.info("⏸️  No pending registrants - entering standby mode")
                            logger.info(f"💤 Standby cycle {wait_cycles} - checking for new registrants in {self.db_check_interval}s...")
                            if self.stop_event.wait(timeout=self.db_check_interval+10):
                                break
                            continue
                        elif wait_cycles > 0:
                            logger.info("🎉 Found pending registrants - resuming active monitoring!")
                            wait_cycles = 0

                    # Get available dates (filtered by target months)
                    self.available_dates = self.get_available_dates(verbose=False)
                    
                    # Check dates (will skip server calls if no dates)
                    result = self.get_timeslots(verbose=False)
                
                except Exception as e:
                    error_msg = f"Error during monitoring cycle: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    emit_error(error_msg, {'exception': str(e)})
                    time.sleep(1)  # Wait before retrying
                    continue
                
                # Track whether auto-registration was attempted (for immediate cycle restart)
                auto_registration_attempted = False
                
                # Attempt auto-registration if slots are available
                if result['total_available_slots'] > 0:
                    logger.info(f"🔥 SLOTS DETECTED! Attempting auto-registration...")
                    
                    # Emit slot found event
                    if result.get('slots_found', False):
                        emit_slot_found(
                            result['registration_data'], 
                            f"Found {result['total_available_slots']} slots!"
                        )
                    
                    if auto_registration:
                        successful_registrations = self.attempt_auto_registration(result['registration_data'])
                        auto_registration_attempted = True
                        
                        if successful_registrations:
                            # Refresh registrant list after successful registrations
                            logger.info("🔄 Refreshing pending registrants after successful registrations...")
                            self.check_pending_registrants()
                            
                            # If no more pending registrants, we can reduce frequency
                            if not self.pending_registrants:
                                logger.info("🎉 All registrants have been registered! Switching to standby mode...")
                        
                        # After auto-registration attempt, immediately start new cycle
                        logger.info("🔄 IMMEDIATE RESTART: Starting new full monitoring cycle after registration attempts...")
                
                # Update cycle duration
                cycle_end = time.time()
                cycle_duration = cycle_end - cycle_start
                with self.stats_lock:
                    self.stats['cycle_duration'] = cycle_duration
                
                # Show current status (limited to once per minute)
                self.print_status_if_needed()
                
                # Check max duration
                if max_duration_minutes:
                    elapsed_minutes = (time.time() - start_time) / 60
                    if elapsed_minutes >= max_duration_minutes:
                        logger.info(f"\n⏰ Stopping after {max_duration_minutes} minutes")
                        break
                
                # If auto-registration was attempted, immediately continue to next cycle
                # Otherwise, wait for the normal check interval
                if auto_registration_attempted:
                    logger.info("⚡ Skipping wait - starting next cycle immediately")
                    continue  # Skip the wait and start new cycle immediately
                
                if self.stop_event.wait(timeout=check_interval):
                    break

            self.stop_event.set()
            logger.info("❌❌❌ Monitoring loop exit.")
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Monitoring stopped by user")
        finally:
            self.stop_event.set()
            self.save_results()
            logger.info("🧹 start_monitoring cleanup completed")
    
    def print_status_if_needed(self):
        """Print current monitoring status once per minute."""
        now = datetime.now()
        
        # Only log status once per minute
        last_log = self.stats.get('last_status_log')
        should_log = (last_log is None or 
                     (now - datetime.fromisoformat(last_log)).seconds >= 60)
        
        if should_log:
            with self.stats_lock:
                self.stats['last_status_log'] = now.isoformat()
            
            # Show detailed info in the periodic status update
            if len(self.pending_registrants) > 0:
                logger.info("📊 Periodic status update:")
                self.get_available_dates(verbose=True)
            
            self.print_status()
    
    def print_status(self):
        """Print current monitoring status with registrant information."""
        now = datetime.now().strftime('%H:%M:%S')
        available_count = len(self.results)
        total_slots = sum(len(slots) for slots in self.results.values())
        pending_count = len(self.pending_registrants)
        cycle_duration = self.stats.get('cycle_duration', 0)
        
        successful_regs = self.stats.get('successful_registrations', 0)
        logger.info(f"[{now}] Status: {available_count} dates with slots, {total_slots} total slots, {pending_count} pending registrants | Cycle: {cycle_duration:.2f}s")
        logger.info(f"🎯 Target months: {sorted(self.target_months) if self.target_months else 'None'} | Server checks: {self.stats['checks_performed']} | ✅ Registered: {successful_regs}")
        
        if self.results:
            logger.info("Current availability:")
            for date_str, slots in sorted(self.results.items()):
                month = datetime.strptime(date_str, "%Y-%m-%d").month
                matching_registrants = [r for r in self.pending_registrants if r.desired_month == month]
                logger.info(f"  📅 {date_str}: {', '.join(slots)} → {len(matching_registrants)} registrants interested")
        else:
            if self.target_months:
                logger.info("  ❌ No slots currently available in target months")
            else:
                logger.info("  ⏸️  No target months - no pending registrants")
    
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
        
        logger.info(f"📁 Results saved to: {filename}")

# def main():
#     print("Real-time Polish Card Appointment Monitor")
#     print("=========================================")
    
#     # Choose monitoring URL
#     print("Select monitoring target:")
#     print("1. pokoj_A1.php (default)")
#     print("2. pokoj_A2.php")
    
#     choice = input("Enter choice (1 or 2, default=1): ").strip()
    
#     if choice == "2":
#         page_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A2.php"
#         monitor = RealTimeAvailabilityMonitor(page_url)
#         monitor.endpoint = "godziny_pokoj_A2.php"
#     else:
#         monitor = RealTimeAvailabilityMonitor()
    
#     # Ask for monitoring duration
#     try:
#         duration_input = input("Enter monitoring duration in minutes (or press Enter for indefinite): ").strip()
#         max_duration = int(duration_input) if duration_input else None
#     except ValueError:
#         max_duration = None
    
#     monitor.start_monitoring(max_duration_minutes=max_duration)

# if __name__ == "__main__":
#     main()