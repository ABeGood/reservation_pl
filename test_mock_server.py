#!/usr/bin/env python3
"""
Test script for the mock registration server.
This script tests all functionality with the existing codebase patterns.
"""

import requests
import json
import time
from datetime import datetime
import base64
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ajax2py import get_timeslots_for_single_date, send_registration_request_with_retry
from capcha import solve_base64

# Mock server configuration
MOCK_BASE_URL = "http://localhost:5000/"
MOCK_ENDPOINT_A1 = "godziny_pokoj_A1.php"
MOCK_ENDPOINT_A2 = "godziny_pokoj_A2.php"

def test_server_availability():
    """Test if mock server is running."""
    print("🔍 Testing server availability...")
    try:
        response = requests.get(MOCK_BASE_URL, timeout=5)
        if response.status_code == 200:
            print("✅ Mock server is running")
            return True
        else:
            print(f"❌ Server returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server: {e}")
        return False

def test_timeslots_api():
    """Test timeslots API endpoints."""
    print("\n🔍 Testing timeslots API...")
    
    test_dates = ["2025-06-26", "2025-07-09", "2025-06-25"]  # Available, available, empty
    
    for endpoint, room in [(MOCK_ENDPOINT_A1, "A1"), (MOCK_ENDPOINT_A2, "A2")]:
        print(f"\n  Testing {room} endpoint ({endpoint}):")
        
        for date in test_dates:
            try:
                date_str, slots = get_timeslots_for_single_date(date, MOCK_BASE_URL, endpoint)
                print(f"    📅 {date}: {len(slots)} slots - {slots}")
            except Exception as e:
                print(f"    ❌ Error for {date}: {e}")

def test_captcha_endpoint():
    """Test CAPTCHA generation."""
    print("\n🔍 Testing CAPTCHA endpoint...")
    
    try:
        # Get CAPTCHA image
        captcha_url = f"{MOCK_BASE_URL}securimage/securimage_show.php"
        response = requests.get(captcha_url)
        
        if response.status_code == 200:
            print("✅ CAPTCHA image generated successfully")
            
            # Convert to base64 for solving
            captcha_base64 = base64.b64encode(response.content).decode('ascii')
            print(f"📸 CAPTCHA image size: {len(response.content)} bytes")
            
            # Test CAPTCHA solving (if API is available)
            try:
                solved_text = solve_base64(captcha_base64)
                print(f"🔍 CAPTCHA solved as: '{solved_text}'")
                return solved_text, response.cookies.get('PHPSESSID')
            except Exception as e:
                print(f"⚠️  CAPTCHA solving failed (API not available): {e}")
                return None, response.cookies.get('PHPSESSID')
        else:
            print(f"❌ CAPTCHA endpoint failed: {response.status_code}")
            return None, None
            
    except Exception as e:
        print(f"❌ CAPTCHA test error: {e}")
        return None, None

def test_registration_flow():
    """Test complete registration flow."""
    print("\n🔍 Testing registration flow...")
    
    # Test data
    registrant_data = {
        'imie': 'Test',
        'nazwisko': 'User', 
        'obywatelstwo': 'Białoruś',
        'email': 'test@example.com',
        'telefon': '123456789',
        'rodzaj_wizyty': 'osoba dorosła'
    }
    
    timeslot_data = {
        'date': '2025-07-09',
        'timeslot_value': 'A209:00'
    }
    
    try:
        print("  📤 Attempting registration with retry mechanism...")
        result = send_registration_request_with_retry(
            base_url=MOCK_BASE_URL,
            registrant_data=registrant_data,
            timeslot_data=timeslot_data,
            max_retries=3
        )
        
        if result.get('success'):
            print("✅ Registration successful!")
            success_data = result.get('success_data', {})
            print(f"   📅 Appointment: {success_data.get('appointment_date')} {success_data.get('appointment_time')}")
            print(f"   🏢 Room: {success_data.get('room')}")
            print(f"   🆔 Code: {success_data.get('registration_code')}")
        else:
            print(f"❌ Registration failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Registration test error: {e}")

def test_api_endpoints():
    """Test additional API endpoints."""
    print("\n🔍 Testing API endpoints...")
    
    try:
        # Test registrations endpoint
        response = requests.get(f"{MOCK_BASE_URL}api/registrations")
        if response.status_code == 200:
            registrations = response.json()
            print(f"✅ API registrations: {len(registrations)} entries")
        
        # Test timeslots status
        response = requests.get(f"{MOCK_BASE_URL}api/timeslots")
        if response.status_code == 200:
            timeslots = response.json()
            total_slots = sum(len(slots) for slots in timeslots.values())
            print(f"✅ API timeslots: {total_slots} total slots across {len(timeslots)} dates")
            
    except Exception as e:
        print(f"❌ API test error: {e}")

def test_error_cases():
    """Test error handling."""
    print("\n🔍 Testing error cases...")
    
    # Test bad CAPTCHA
    try:
        data = {
            'imie': 'Test',
            'nazwisko': 'User',
            'obywatelstwo': 'Białoruś', 
            'email': 'test@example.com',
            'telefon': '123456789',
            'rodzaj_wizyty': 'osoba dorosła',
            'datepicker': '2025-07-09',
            'godzina': 'A209:00',
            'captcha_code': 'wrongcode'
        }
        
        response = requests.post(f"{MOCK_BASE_URL}send.php", data=data)
        if "nieprawidłowy" in response.text:
            print("✅ Bad CAPTCHA handling works")
        else:
            print("❌ Bad CAPTCHA not detected")
            
    except Exception as e:
        print(f"❌ Error case test failed: {e}")

def reset_server_data():
    """Reset server data for clean testing."""
    print("\n🧹 Resetting server data...")
    try:
        response = requests.post(f"{MOCK_BASE_URL}api/reset")
        if response.status_code == 200:
            print("✅ Server data reset successfully")
        else:
            print(f"❌ Reset failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Reset error: {e}")

def main():
    """Run all tests."""
    print("🧪 Mock Server Test Suite")
    print("=" * 50)
    
    # Check if server is running
    if not test_server_availability():
        print("\n❌ Please start the mock server first:")
        print("   python mock_server.py")
        return
    
    # Reset data for clean testing
    reset_server_data()
    
    # Run tests
    test_timeslots_api()
    test_captcha_endpoint()
    test_registration_flow()
    test_api_endpoints()
    test_error_cases()
    
    print("\n" + "=" * 50)
    print("🎉 Test suite completed!")
    print("\n📋 Manual testing URLs:")
    print(f"   Main page: {MOCK_BASE_URL}")
    print(f"   Room A1: {MOCK_BASE_URL}pokoj_A1.php")
    print(f"   Room A2: {MOCK_BASE_URL}pokoj_A2.php")

if __name__ == "__main__":
    main()