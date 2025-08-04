import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
import logging
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PolishCardFormFiller:
    def __init__(self, json_file_path, webdriver_path=None):
        """
        Initialize the form filler with JSON data source
        
        Args:
            json_file_path (str): Path to JSON file containing form data
            webdriver_path (str): Path to ChromeDriver executable (optional)
        """
        self.json_file_path = json_file_path
        self.webdriver_path = webdriver_path
        self.driver = None
        self.wait = None
        
    def load_json_data(self):
        """Load and validate JSON data"""
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                logger.info(f"Successfully loaded data from {self.json_file_path}")
                return data
        except FileNotFoundError:
            logger.error(f"JSON file not found: {self.json_file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {e}")
            raise
    
    def setup_driver(self):
        """Configure and initialize Chrome WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Uncomment the line below to run in headless mode
        # chrome_options.add_argument("--headless")
        
        try:
            if self.webdriver_path:
                service = Service(self.webdriver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 10)
            logger.info("WebDriver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    def navigate_to_form(self, url):
        """Navigate to the Polish Card appointment form"""
        try:
            self.driver.get(url)
            logger.info(f"Navigated to: {url}")
            
            # Wait for the form to be present
            self.wait.until(EC.presence_of_element_located((By.ID, "for_rezerwacji")))
            logger.info("Form loaded successfully")
            
        except TimeoutException:
            logger.error("Timeout waiting for form to load")
            raise
    
    def fill_name_fields(self, person_data):
        """
        Fill name and surname fields from person data
        
        Args:
            person_data (dict): Dictionary containing 'name' and 'surname' keys
        """
        try:
            # Validate required fields in data
            if 'name' not in person_data or 'surname' not in person_data:
                raise ValueError("JSON data must contain 'name' and 'surname' fields")
            
            # Wait for and fill the name field (imie)
            name_field = self.wait.until(
                EC.element_to_be_clickable((By.ID, "imie"))
            )
            name_field.clear()
            name_field.send_keys(person_data['name'])
            logger.info(f"Name field filled with: {person_data['name']}")
            
            # Wait for and fill the surname field (nazwisko)
            surname_field = self.wait.until(
                EC.element_to_be_clickable((By.ID, "nazwisko"))
            )
            surname_field.clear()
            surname_field.send_keys(person_data['surname'])
            logger.info(f"Surname field filled with: {person_data['surname']}")
            
            # Optional: Add a small delay to ensure fields are properly filled
            time.sleep(1)
            
            # Verify the fields were filled correctly
            filled_name = name_field.get_attribute('value')
            filled_surname = surname_field.get_attribute('value')
            
            if filled_name != person_data['name']:
                logger.warning(f"Name field verification failed. Expected: {person_data['name']}, Got: {filled_name}")
            if filled_surname != person_data['surname']:
                logger.warning(f"Surname field verification failed. Expected: {person_data['surname']}, Got: {filled_surname}")
            
            logger.info("Name and surname fields filled successfully")
            
        except TimeoutException:
            logger.error("Timeout waiting for name/surname fields to be clickable")
            raise
        except NoSuchElementException:
            logger.error("Name or surname field not found on the page")
            raise
    
    def fill_additional_fields(self, person_data):
        """Fill additional form fields if provided in JSON data"""
        try:
            # Fill citizenship if provided
            if 'citizenship' in person_data:
                citizenship_dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "obywatel"))
                )
                citizenship_dropdown.send_keys(person_data['citizenship'])
                logger.info(f"Citizenship filled with: {person_data['citizenship']}")
            
            # Fill email if provided
            if 'email' in person_data:
                email_field = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "email"))
                )
                email_field.clear()
                email_field.send_keys(person_data['email'])
                logger.info(f"Email filled with: {person_data['email']}")
            
            # Fill phone if provided
            if 'phone' in person_data:
                phone_field = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "telefon"))
                )
                phone_field.clear()
                phone_field.send_keys(person_data['phone'])
                logger.info(f"Phone filled with: {person_data['phone']}")
            
            # Fill application type if provided
            if 'application_type' in person_data:
                app_type_dropdown = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "rodzaj"))
                )
                app_type_dropdown.send_keys(person_data['application_type'])
                logger.info(f"Application type filled with: {person_data['application_type']}")
                
        except TimeoutException:
            logger.warning("Timeout waiting for additional fields - continuing with basic fields only")
        except Exception as e:
            logger.warning(f"Error filling additional fields: {e}")
    
    def process_form(self, url, fill_additional=False):
        """
        Main method to process the form filling
        
        Args:
            url (str): URL of the form
            fill_additional (bool): Whether to fill additional fields beyond name/surname
        """
        try:
            # Load JSON data
            data = self.load_json_data()
            
            # Setup WebDriver
            self.setup_driver()
            
            # Navigate to form
            self.navigate_to_form(url)
            
            # Handle single person or multiple people
            if isinstance(data, list):
                logger.info(f"Processing {len(data)} people from JSON file")
                for i, person in enumerate(data):
                    logger.info(f"Processing person {i+1}: {person.get('name', 'Unknown')} {person.get('surname', 'Unknown')}")
                    
                    if i > 0:  # Refresh page for subsequent entries
                        self.driver.refresh()
                        time.sleep(2)
                    
                    self.fill_name_fields(person)
                    
                    if fill_additional:
                        self.fill_additional_fields(person)
                    
                    # Pause between entries
                    if i < len(data) - 1:
                        time.sleep(3)
            else:
                logger.info("Processing single person from JSON file")
                self.fill_name_fields(data)
                
                if fill_additional:
                    self.fill_additional_fields(data)
            
            logger.info("Form filling completed successfully")
            
            # Keep browser open for manual review/completion
            input("Press Enter to close the browser...")
            
        except Exception as e:
            logger.error(f"Error during form processing: {e}")
            raise
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")

def create_sample_json():
    """Create a sample JSON file for testing"""
    sample_data = [
        {
            "name": "Jan",
            "surname": "Kowalski",
            "citizenship": "Ukraina",
            "email": "jan.kowalski@example.com",
            "phone": "123456789",
            "application_type": "osoba dorosła"
        },
        {
            "name": "Anna",
            "surname": "Nowak",
            "citizenship": "Białoruś",
            "email": "anna.nowak@example.com",
            "phone": "987654321",
            "application_type": "osoba dorosła i małoletnie dzieci"
        }
    ]
    
    with open('people_data.json', 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)
    
    print("Sample JSON file 'people_data.json' created successfully")


class DatePickerScanner:
    def __init__(self, webdriver_path=None):
        """
        Initialize the date picker scanner
        
        Args:
            webdriver_path (str): Path to ChromeDriver executable (optional)
        """
        self.webdriver_path = webdriver_path
        self.driver = None
        self.wait = None
        self.available_slots = {}
        self.current_month = None
        self.current_year = None
        
    def setup_driver(self):
        """Configure and initialize Chrome WebDriver"""
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Uncomment for headless mode
        # chrome_options.add_argument("--headless")
        
        try:
            if self.webdriver_path:
                service = Service(self.webdriver_path)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.wait = WebDriverWait(self.driver, 15)
            logger.info("WebDriver initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    def navigate_to_form(self, url):
        """Navigate to the Polish Card appointment form"""
        try:
            self.driver.get(url)
            logger.info(f"Navigated to: {url}")
            
            # Wait for the form to be present
            self.wait.until(EC.presence_of_element_located((By.ID, "for_rezerwacji")))
            logger.info("Form loaded successfully")
            
        except TimeoutException:
            logger.error("Timeout waiting for form to load")
            raise
    
    def click_datepicker(self):
        """Click the datepicker input to open calendar"""
        try:
            datepicker_input = self.wait.until(
                EC.element_to_be_clickable((By.ID, "datepicker"))
            )
            
            # Scroll element into view
            self.driver.execute_script("arguments[0].scrollIntoView(true);", datepicker_input)
            time.sleep(0.2)
            
            # Try direct click first
            try:
                datepicker_input.click()
                logger.info("Datepicker clicked successfully")
            except ElementClickInterceptedException:
                # Use JavaScript click as fallback
                self.driver.execute_script("arguments[0].click();", datepicker_input)
                logger.info("Datepicker clicked using JavaScript")
            
            # Wait for calendar to appear
            self.wait.until(
                EC.visibility_of_element_located((By.CLASS_NAME, "ui-datepicker-calendar"))
            )
            logger.info("Calendar opened successfully")
            return True
            
        except TimeoutException:
            logger.error("Timeout waiting for datepicker or calendar")
            return False
        except Exception as e:
            logger.error(f"Error clicking datepicker: {e}")
            return False
    
    def get_calendar_info(self):
        """Get current month and year from calendar header"""
        try:
            month_element = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "ui-datepicker-month"))
            )
            year_element = self.driver.find_element(By.CLASS_NAME, "ui-datepicker-year")
            
            month_text = month_element.text.strip()
            year_text = year_element.text.strip()
            
            # Polish month names mapping
            polish_months = {
                'Styczeń': 1, 'Luty': 2, 'Marzec': 3, 'Kwiecień': 4,
                'Maj': 5, 'Czerwiec': 6, 'Lipiec': 7, 'Sierpień': 8,
                'Wrzesień': 9, 'Październik': 10, 'Listopad': 11, 'Grudzień': 12
            }
            
            self.current_month = polish_months.get(month_text, 8)  # Default to August
            self.current_year = int(year_text)
            
            logger.info(f"Current calendar view: {month_text} {year_text} ({self.current_month}/{self.current_year})")
            return True
            
        except Exception as e:
            logger.error(f"Error getting calendar info: {e}")
            return False
    
    def get_clickable_dates(self):
        """Get all clickable dates from current calendar view"""
        try:
            calendar_table = self.driver.find_element(By.CLASS_NAME, "ui-datepicker-calendar")
            
            # Find all clickable date cells
            clickable_dates = calendar_table.find_elements(
                By.CSS_SELECTOR, 
                "td[data-handler='selectDay'] a"
            )
            
            dates_info = []
            for date_element in clickable_dates:
                try:
                    day = int(date_element.text.strip())
                    parent_td = date_element.find_element(By.XPATH, "./..")
                    
                    # Get data attributes
                    data_month = int(parent_td.get_attribute("data-month"))
                    data_year = int(parent_td.get_attribute("data-year"))
                    
                    # Check if date is today or future
                    date_obj = datetime(data_year, data_month + 1, day)  # data-month is 0-based
                    today = datetime.now()
                    
                    if date_obj.date() >= today.date():
                        dates_info.append({
                            'element': date_element,
                            'day': day,
                            'month': data_month + 1,
                            'year': data_year,
                            'date_obj': date_obj,
                            'date_str': date_obj.strftime('%Y-%m-%d')
                        })
                
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Error parsing date element: {e}")
                    continue
            
            # Sort by date
            dates_info.sort(key=lambda x: x['date_obj'])
            logger.info(f"Found {len(dates_info)} clickable dates in current view")
            return dates_info
            
        except NoSuchElementException:
            logger.error("Calendar table not found")
            return []
        except Exception as e:
            logger.error(f"Error getting clickable dates: {e}")
            return []
    
    def close_calendar(self):
        """Close the calendar if it's open"""
        try:
            # Try clicking elsewhere to close calendar
            form_element = self.driver.find_element(By.ID, "for_rezerwacji")
            form_element.click()
            time.sleep(0.5)
            
            # Alternative: Press Escape key
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.3)
            
            logger.debug("Calendar closed")
            
        except Exception as e:
            logger.debug(f"Error closing calendar (may already be closed): {e}")
    
    def click_specific_date(self, date_info):
        """
        Click on a specific date in the calendar
        
        Args:
            date_info (dict): Date information containing element reference and date details
        """
        try:
            # We need to find the date element again since the calendar was reopened
            calendar_table = self.driver.find_element(By.CLASS_NAME, "ui-datepicker-calendar")
            
            # Find the specific date element by matching day, month, year
            target_day = date_info['day']
            target_month = date_info['month'] - 1  # Convert to 0-based for data-month
            target_year = date_info['year']
            
            # Find all clickable date cells
            clickable_dates = calendar_table.find_elements(
                By.CSS_SELECTOR, 
                "td[data-handler='selectDay'] a"
            )
            
            for date_element in clickable_dates:
                try:
                    day = int(date_element.text.strip())
                    parent_td = date_element.find_element(By.XPATH, "./..")
                    
                    # Get data attributes
                    data_month = int(parent_td.get_attribute("data-month"))
                    data_year = int(parent_td.get_attribute("data-year"))
                    
                    # Check if this matches our target date
                    if day == target_day and data_month == target_month and data_year == target_year:
                        # Scroll element into view
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", date_element)
                        time.sleep(0.3)
                        
                        # Click the date
                        date_element.click()
                        logger.info(f"Successfully clicked date: {date_info['date_str']}")
                        return True
                        
                except (ValueError, AttributeError):
                    continue
            
            logger.error(f"Could not find date element for {date_info['date_str']}")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking specific date {date_info['date_str']}: {e}")
            return False
    
    def print_scan_summary(self, total_dates_checked):
        """Print detailed scan summary"""
        logger.info("\n" + "=" * 60)
        logger.info("SCAN COMPLETE - DETAILED SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total dates checked: {total_dates_checked}")
        logger.info(f"Dates with available slots: {len(self.available_slots)}")
        
        if self.available_slots:
            logger.info(f"\n{'='*30} AVAILABLE APPOINTMENTS {'='*30}")
            
            # Group by month for better readability
            from collections import defaultdict
            slots_by_month = defaultdict(list)
            
            for date_str, slots in sorted(self.available_slots.items()):
                month_key = date_str[:7]  # YYYY-MM
                slots_by_month[month_key].append((date_str, slots))
            
            for month, date_slots in sorted(slots_by_month.items()):
                logger.info(f"\n📅 {month}:")
                for date_str, slots in date_slots:
                    logger.info(f"   {date_str}: {', '.join(slots)}")
            
            # Statistics
            total_slots = sum(len(slots) for slots in self.available_slots.values())
            logger.info(f"\n📊 STATISTICS:")
            logger.info(f"   Total available time slots: {total_slots}")
            logger.info(f"   Average slots per available date: {total_slots/len(self.available_slots):.1f}")
            
            # Best days (most slots)
            best_dates = sorted(self.available_slots.items(), 
                              key=lambda x: len(x[1]), reverse=True)[:3]
            logger.info(f"\n🏆 BEST AVAILABILITY:")
            for i, (date, slots) in enumerate(best_dates, 1):
                logger.info(f"   {i}. {date}: {len(slots)} slots ({', '.join(slots)})")
        else:
            logger.info("\n❌ No available appointment slots found in the scanned period")
            logger.info("   Consider:")
            logger.info("   - Checking again later (slots may become available)")
            logger.info("   - Expanding the search to more months")
            logger.info("   - Verifying the website is working correctly")
    
    def check_time_slots(self):
        """Check for available time slots after selecting a date"""
        try:
            # Wait for the time slot container to update
            time.sleep(2)
            
            # Look for time slot elements in the godzina container
            time_slot_container = self.driver.find_element(By.ID, "class_godzina")
            
            # First check for "Brak wolnych godzin" message
            maroon_fonts = time_slot_container.find_elements(By.CSS_SELECTOR, "font[color='maroon']")
            for font in maroon_fonts:
                if "brak wolnych godzin" in font.text.lower():
                    logger.debug("Found 'Brak wolnych godzin' message")
                    return []
            
            # Check for available time slots - look for radio inputs with class="intro"
            time_slots = []
            radio_inputs = time_slot_container.find_elements(By.CSS_SELECTOR, "input[type='radio'][name='godzina'].intro")
            
            for radio in radio_inputs:
                # Get the value (format: A209:00)
                value = radio.get_attribute("value")
                radio_id = radio.get_attribute("id")
                
                if value:
                    # Extract time from value (A209:00 -> 09:00)
                    if ":" in value:
                        time_part = value.split(":")
                        if len(time_part) >= 2:
                            # Handle format like A209:00 -> 09:00
                            if len(time_part[0]) > 2:
                                hour = time_part[0][-2:]  # Get last 2 digits
                                minute = time_part[1]
                                clean_time = f"{hour}:{minute}"
                            else:
                                clean_time = f"{time_part[0]}:{time_part[1]}"
                            
                            time_slots.append(clean_time)
                            logger.debug(f"Found time slot: {clean_time} (value: {value})")
            
            # Alternative: look for labels associated with radio buttons
            if not time_slots:
                labels = time_slot_container.find_elements(By.CSS_SELECTOR, "label")
                for label in labels:
                    label_text = label.text.strip()
                    if ":" in label_text and len(label_text) <= 6:  # Time format like 09:00
                        label_for = label.get_attribute("for")
                        if label_for:
                            try:
                                associated_radio = self.driver.find_element(By.ID, label_for)
                                if associated_radio.get_attribute("name") == "godzina":
                                    time_slots.append(label_text)
                                    logger.debug(f"Found time slot via label: {label_text}")
                            except NoSuchElementException:
                                continue
            
            return time_slots
            
        except NoSuchElementException:
            logger.warning("Time slot container not found")
            return []
        except Exception as e:
            logger.warning(f"Error checking time slots: {e}")
            return []
    
    def navigate_to_next_month(self):
        """Navigate to next month in calendar"""
        try:
            next_button = self.driver.find_element(
                By.CSS_SELECTOR, 
                ".ui-datepicker-next:not(.ui-state-disabled)"
            )
            next_button.click()
            time.sleep(1)
            
            logger.info("Navigated to next month")
            return True
            
        except NoSuchElementException:
            logger.info("No next month available or button disabled")
            return False
        except Exception as e:
            logger.error(f"Error navigating to next month: {e}")
            return False
    
    def scan_all_available_dates(self, url, max_months=3):
        """
        Main method to scan all available dates for appointment slots
        Following the exact workflow:
        1. Click datepicker → 2. Click date → 3. Calendar closes → 4. Check slots → 5. Repeat
        
        Args:
            url (str): URL of the appointment form
            max_months (int): Maximum number of months to scan
        """
        try:
            self.setup_driver()
            self.navigate_to_form(url)
            
            months_scanned = 0
            total_dates_checked = 0
            
            while months_scanned < max_months:
                logger.info(f"\n{'='*60}")
                logger.info(f"SCANNING MONTH {months_scanned + 1}/{max_months}")
                logger.info(f"{'='*60}")
                
                # Step 1: Open calendar to get list of clickable dates
                if not self.click_datepicker():
                    logger.error("Failed to open calendar")
                    break
                
                # Get calendar info and all available dates for this month
                if not self.get_calendar_info():
                    logger.error("Failed to get calendar info")
                    break
                
                clickable_dates = self.get_clickable_dates()
                
                if not clickable_dates:
                    logger.info("No clickable dates found in current month")
                    # Try to navigate to next month
                    if self.navigate_to_next_month():
                        months_scanned += 1
                        continue
                    else:
                        logger.info("No more months available")
                        break
                
                logger.info(f"Found {len(clickable_dates)} clickable dates in current month")
                
                # Close the calendar by clicking elsewhere or pressing Escape
                self.close_calendar()
                
                # Now iterate through each date systematically
                for i, date_info in enumerate(clickable_dates):
                    logger.info(f"\nProcessing date {i+1}/{len(clickable_dates)}: {date_info['date_str']}")
                    
                    # Step 1: Click datepicker to open calendar
                    if not self.click_datepicker():
                        logger.warning(f"Failed to open calendar for date {date_info['date_str']}")
                        continue
                    
                    # Step 2: Click on the specific date
                    if not self.click_specific_date(date_info):
                        logger.warning(f"Failed to click date {date_info['date_str']}")
                        continue
                    
                    # Step 3: Calendar closes automatically after clicking date
                    # Wait a moment for calendar to close and page to process
                    time.sleep(0.3)
                    
                    # Step 4: Check for available time slots
                    available_slots = self.check_time_slots()
                    total_dates_checked += 1
                    
                    if available_slots:
                        self.available_slots[date_info['date_str']] = available_slots
                        logger.info(f"✓ Date {date_info['date_str']}: {len(available_slots)} slots available")
                        for slot in available_slots:
                            logger.info(f"    - {slot}")

                        
                    else:
                        logger.info(f"✗ Date {date_info['date_str']}: No available time slots")
                    
                    # Small delay between date checks
                    time.sleep(0.2)
                
                # Step 10: Try to navigate to next month
                logger.info(f"\nCompleted scanning month {months_scanned + 1}")
                
                # Open calendar to navigate to next month
                if not self.click_datepicker():
                    logger.warning("Could not open calendar to navigate to next month")
                    break
                
                if self.navigate_to_next_month():
                    months_scanned += 1
                    # Close the calendar again
                    self.close_calendar()
                    logger.info(f"Successfully navigated to next month")
                else:
                    logger.info("No more months available - ending scan")
                    break
            
            # Final summary
            self.print_scan_summary(total_dates_checked)
            
            # Save results to JSON
            self.save_results()
            
            # Keep browser open for manual review
            input("\nPress Enter to close the browser...")
            
        except Exception as e:
            logger.error(f"Error during date scanning: {e}")
            raise
        finally:
            self.cleanup()
    
    def save_results(self):
        """Save scan results to JSON file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"appointment_slots_{timestamp}.json"
            
            results = {
                "scan_timestamp": datetime.now().isoformat(),
                "total_available_dates": len(self.available_slots),
                "available_slots": self.available_slots
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Results saved to: {filename}")
            
        except Exception as e:
            logger.error(f"Error saving results: {e}")
    
    def cleanup(self):
        """Clean up WebDriver resources"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")


def main():
    """Main execution function"""
    # Configuration
    JSON_FILE_PATH = "people_data.json"
    FORM_URL = "https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A2.php"  # Replace with actual URL
    WEBDRIVER_PATH = None  # Set path to chromedriver if not in PATH
    MAX_MONTHS = 3
    
    # Create sample JSON if it doesn't exist
    import os
    if not os.path.exists(JSON_FILE_PATH):
        create_sample_json()
        print(f"Created sample JSON file: {JSON_FILE_PATH}")
        print("Please update the JSON file with your actual data and run the script again.")
        return
    
    # Initialize and run form filler
    form_filler = PolishCardFormFiller(JSON_FILE_PATH, WEBDRIVER_PATH)
    scanner = DatePickerScanner(WEBDRIVER_PATH)
    
    try:
        # Process form with basic fields (name + surname only)
        # form_filler.process_form(FORM_URL, fill_additional=False)
        
        # To fill additional fields, use:
        # form_filler.process_form(FORM_URL, fill_additional=True)

        scanner.scan_all_available_dates(FORM_URL, MAX_MONTHS)
        
    except Exception as e:
        logger.error(f"Script execution failed: {e}")

if __name__ == "__main__":
    main()