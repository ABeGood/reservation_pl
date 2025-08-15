import requests
from datetime import datetime, timedelta
import time
import re
import base64
from dotenv import load_dotenv
from capcha import solve_capcha_base64

# Load environment variables for CAPTCHA solving
load_dotenv()


def parse_time_slots(html_response):
    """Extract available time slots from HTML response"""
    if "Brak wolnych godzin" in html_response:
        return []
    
    # Extract time slots from radio inputs
    # Pattern: <label for="A209:00">09:00</label>
    time_pattern = r'<label for="[^"]*">(\d{2}:\d{2})</label>'
    times = re.findall(time_pattern, html_response)
    
    return times

def get_timeslots_for_single_date(date_str, base_url:str, endpoint:str):
        """Check availability for a single date using existing ajax2py pattern."""
        url = f"{base_url}{endpoint}"
        
        data = {'godzina': date_str}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': base_url,
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        try:
            # Sleep for server courtesy before each request
            time.sleep(0.2)
            
            response = requests.post(url, data=data, headers=headers, timeout=10)
            if response.status_code == 200:
                # Reuse existing parse_time_slots function
                slots = parse_time_slots(response.text)
                return (date_str, slots)
            else:
                return (date_str, [])
        except Exception as e:
            return (date_str, [])

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
    return _send_registration_attempt(base_url, registrant_data, timeslot_data, captcha_code, session_id)


def send_registration_request_with_retry(base_url: str, registrant_data: dict, timeslot_data: dict, 
                                       max_retries: int = 12, session_id: str = None):
    """
    Send registration request with CAPTCHA retry mechanism.
    
    Args:
        base_url (str): Base URL of the appointment system
        registrant_data (dict): Personal information (same as send_registration_request)
        timeslot_data (dict): Appointment slot (same as send_registration_request)
        captcha_solver_func (callable): Function to solve CAPTCHA, should return dict with 'result' key
                                       Function signature: captcha_solver_func(captcha_image_base64: str) -> dict
        max_retries (int): Maximum number of retry attempts (default: 3)
        session_id (str, optional): PHPSESSID cookie value. If None, will get new session for each attempt.
    
    Returns:
        dict: Response with success status, details, and retry information
    """
    for attempt in range(max_retries + 1):
        try:
            # Get fresh session and CAPTCHA for each attempt
            if not session_id or attempt > 0:
                session_id = get_session_id(base_url)
                if not session_id:
                    return {
                        'success': False,
                        'error': 'Failed to obtain session ID',
                        'attempt': attempt + 1,
                        'max_retries': max_retries
                    }
            
            # Get new CAPTCHA image
            captcha_data = get_captcha_image(base_url, session_id)
            if not captcha_data['success']:
                return {
                    'success': False,
                    'error': f'Failed to fetch CAPTCHA: {captcha_data.get("error", "Unknown error")}',
                    'attempt': attempt + 1,
                    'max_retries': max_retries
                }
            
            # Solve CAPTCHA
            captcha_solution = solve_capcha_base64(captcha_data['image_base64'])
            if not captcha_solution.get('result'):
                return {
                    'success': False,
                    'error': f'CAPTCHA solving failed: {captcha_solution}',
                    'attempt': attempt + 1,
                    'max_retries': max_retries
                }
            
            captcha_code = captcha_solution['result']
            
            # Attempt registration
            result = _send_registration_attempt(base_url, registrant_data, timeslot_data, captcha_code, session_id)
            
            # Check if this was a CAPTCHA error
            if _is_captcha_error(result):
                if attempt < max_retries:
                    print(f"CAPTCHA error detected (attempt {attempt + 1}/{max_retries + 1}). Retrying with new CAPTCHA...")
                    time.sleep(0.2)  # Brief delay between attempts
                    continue
                else:
                    result['error'] = 'Maximum CAPTCHA retry attempts exceeded'
                    result['attempt'] = attempt + 1
                    result['max_retries'] = max_retries
                    return result
            
            # Success or non-CAPTCHA error - return result
            result['attempt'] = attempt + 1
            result['max_retries'] = max_retries
            return result
            
        except Exception as e:
            if attempt < max_retries:
                print(f"Unexpected error on attempt {attempt + 1}: {e}. Retrying...")
                time.sleep(1)
                continue
            else:
                return {
                    'success': False,
                    'error': f'Unexpected error after {max_retries + 1} attempts: {str(e)}',
                    'attempt': attempt + 1,
                    'max_retries': max_retries
                }
    
    return {
        'success': False,
        'error': 'All retry attempts failed',
        'attempt': max_retries + 1,
        'max_retries': max_retries
    }


def _send_registration_attempt(base_url: str, registrant_data: dict, timeslot_data: dict, captcha_code: str, session_id: str = None):
    """
    Internal function to send a single registration attempt.
    This is the original send_registration_request logic extracted for reuse.
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
            
            # Check if this is a success page
            if 'dane rejestracyjne:' in response_text and 'kod zgłoszenia-' in response_text:
                result['success'] = True
                result['message'] = 'Registration successful'
                
                # Parse success data
                success_data = parse_success_response(response.text)
                if success_data.get('success'):
                    result['success_data'] = success_data
                    result['message'] = f'Registration successful - Code: {success_data.get("registration_code")}'
                else:
                    result['parse_error'] = success_data.get('error')
                    result['message'] = 'Registration successful but failed to parse details'
                    
            elif any(success_phrase in response_text for success_phrase in [
                'rezerwacja została', 'potwierdzenie', 'sukces', 'zarezerwowano'
            ]):
                result['success'] = True
                result['message'] = 'Registration appears successful'
            # Check for specific reservation error
            elif 'błąd rezerwacji' in response_text:
                result['message'] = 'Reservation error - check availability for selected date/time'
            # Check if this is a wrong CAPCHA page
            elif any(error_phrase in response_text for error_phrase in [
                'błąd', 'error', 'nieprawidłowy', 'captcha', 'przez ciebie'
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


def _is_captcha_error(result: dict) -> bool:
    """
    Check if the response indicates a CAPTCHA error.
    
    Args:
        result (dict): Response from _send_registration_attempt
        
    Returns:
        bool: True if this is a CAPTCHA error, False otherwise
    """
    if not result.get('response_text'):
        return False
    
    response_text = result['response_text'].lower()
    
    # Check for specific CAPTCHA error indicators
    captcha_error_phrases = [
        'kod z obrazka przepisany przez ciebie jest nieprawidłowy',  # Polish: "The code from the image you entered is incorrect"
        'nieprawidłowy kod captcha',
        'błędny kod z obrazka',
        'captcha code is incorrect',
        'invalid captcha'
    ]
    
    return any(phrase in response_text for phrase in captcha_error_phrases)


def get_captcha_image(base_url: str, session_id: str) -> dict:
    """
    Fetch CAPTCHA image from the appointment system.
    
    Args:
        base_url (str): Base URL of the appointment system
        session_id (str): PHPSESSID cookie value
        
    Returns:
        dict: Response with success status and base64 image data
    """
    captcha_url = f"{base_url}securimage/securimage_show.php" if not base_url.endswith('/') else f"{base_url}securimage/securimage_show.php"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': base_url
    }
    
    cookies = {
        'PHPSESSID': session_id
    }
    
    try:
        response = requests.get(captcha_url, headers=headers, cookies=cookies, timeout=10)
        
        if response.status_code == 200:
            # Convert image to base64
            image_base64 = base64.b64encode(response.content).decode('ascii')
            
            return {
                'success': True,
                'image_base64': image_base64,
                'content_type': response.headers.get('content-type', 'image/png')
            }
        else:
            return {
                'success': False,
                'error': f'HTTP error {response.status_code}'
            }
            
    except requests.RequestException as e:
        return {
            'success': False,
            'error': f'Request failed: {str(e)}'
        }


def parse_success_response(response_text: str) -> dict:
    """
    Parse success response HTML to extract registration details.
    
    Args:
        response_text (str): HTML response from successful registration
        
    Returns:
        dict: Parsed registration data with keys:
            - success (bool): True if parsing successful
            - name (str): Registrant's first name
            - surname (str): Registrant's last name  
            - email (str): Email address
            - phone (str): Phone number
            - appointment_datetime (str): Full appointment date and time
            - appointment_date (str): Appointment date (YYYY-MM-DD)
            - appointment_time (str): Appointment time (HH:MM)
            - room (str): Room/location (e.g., "A2 pokoj 25")
            - citizenship (str): Citizenship
            - application_type (str): Type of application
            - registration_code (str): System-generated registration code
    """
    import re
    
    try:
        # Extract name (pattern: Dane rejestracyjne:&nbsp<t class='text'>Name &nbsp Surname</t>)
        name_pattern = r"Dane rejestracyjne:&nbsp<t class='text'>([^<]+)</t>"
        name_match = re.search(name_pattern, response_text)
        if not name_match:
            return {'success': False, 'error': 'Could not parse registrant name'}
        
        full_name = name_match.group(1).strip()
        # Handle format "Name &nbsp Surname" - split by &nbsp or whitespace
        name_parts = [part.strip() for part in full_name.replace('&nbsp', ' ').split() if part.strip()]
        if len(name_parts) < 2:
            return {'success': False, 'error': f'Invalid name format: {full_name}'}
        
        name = name_parts[0]
        surname = ' '.join(name_parts[1:])
        
        # Extract email (pattern: Adres e-mail-<t class='text'>&nbspgriss7473@gmail.com</t>)
        email_pattern = r"Adres e-mail-<t class='text'>&nbsp([^<]+)</t>"
        email_match = re.search(email_pattern, response_text)
        if not email_match:
            return {'success': False, 'error': 'Could not parse email'}
        email = email_match.group(1).strip()
        
        # Extract phone (pattern: Telefon-<t class='text'>&nbsp555987654</t>)
        phone_pattern = r"Telefon-<t class='text'>&nbsp([^<]+)</t>"
        phone_match = re.search(phone_pattern, response_text)
        if not phone_match:
            return {'success': False, 'error': 'Could not parse phone'}
        phone = phone_match.group(1).strip()
        
        # Extract appointment details (pattern: <t class='text'>2025-07-09 &nbsp  09:00 &nbsp A2 pokoj 25</t>)
        appointment_pattern = r"Data rezerwacji,godzina,stanowisko-<br><t class='text'>([^<]+)</t>"
        appointment_match = re.search(appointment_pattern, response_text)
        if not appointment_match:
            return {'success': False, 'error': 'Could not parse appointment details'}
        
        appointment_text = appointment_match.group(1).strip()
        # Parse format: "2025-07-09 &nbsp  09:00 &nbsp A2 pokoj 25" - handle &nbsp
        appointment_clean = appointment_text.replace('&nbsp', ' ')
        appointment_parts = [part.strip() for part in appointment_clean.split() if part.strip()]
        if len(appointment_parts) < 3:
            return {'success': False, 'error': f'Invalid appointment format: {appointment_text}'}
        
        appointment_date = appointment_parts[0]
        appointment_time = appointment_parts[1]
        room = ' '.join(appointment_parts[2:])
        
        # Extract citizenship (pattern: Obywatelstwo -<t class='text'>&nbsp</t>)
        citizenship_pattern = r"Obywatelstwo -<t class='text'>&nbsp([^<]*)</t>"
        citizenship_match = re.search(citizenship_pattern, response_text)
        if not citizenship_match:
            return {'success': False, 'error': 'Could not parse citizenship'}
        citizenship = citizenship_match.group(1).strip()
        
        # Extract application type (pattern: Dotyczy -<t class='text'>&nbsposoba dorosła</t>)
        app_type_pattern = r"Dotyczy -<t class='text'>&nbsp([^<]+)</t>"
        app_type_match = re.search(app_type_pattern, response_text)
        if not app_type_match:
            return {'success': False, 'error': 'Could not parse application type'}
        application_type = app_type_match.group(1).strip()
        
        # Extract registration code (pattern: Kod zgłoszenia-<t class='text'>&nbsp9569bf</t>)
        code_pattern = r"Kod zgłoszenia-<t class='text'>&nbsp([^<]+)</t>"
        code_match = re.search(code_pattern, response_text)
        if not code_match:
            return {'success': False, 'error': 'Could not parse registration code'}
        registration_code = code_match.group(1).strip()
        
        return {
            'success': True,
            'name': name,
            'surname': surname,
            'email': email,
            'phone': phone,
            'appointment_datetime': f"{appointment_date} {appointment_time}",
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
            'room': room,
            'citizenship': citizenship,
            'application_type': application_type,
            'registration_code': registration_code
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Parsing failed: {str(e)}'
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
