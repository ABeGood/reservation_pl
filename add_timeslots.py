#!/usr/bin/env python3
"""
Script to add timeslots to the mock server while it's running.
Usage: python add_timeslots.py
"""

import requests
import json
from datetime import datetime, timedelta

def add_timeslots(timeslots_data):
    """Add timeslots to the mock server."""
    url = "http://localhost:5000/api/timeslots/add"
    
    try:
        response = requests.post(url, json=timeslots_data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS:")
            print(f"   {result['message']}")
            print(f"   Updated dates: {', '.join(result['updated_dates'])}")
            return True
        else:
            error_data = response.json()
            print(f"❌ ERROR: {error_data.get('error', 'Unknown error')}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to mock server at localhost:5000")
        print("   Make sure mock_server.py is running first!")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def generate_sample_data():
    """Generate sample timeslot data for testing."""
    today = datetime.now().date()
    
    # Generate dates for next 7 days
    sample_data = {}
    for i in range(1, 8):  # Next 7 days
        date = today + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        
        # Skip weekends
        if date.weekday() < 5:  # Monday=0, Sunday=6
            # Add some random timeslots
            if i % 2 == 0:  # Even days
                sample_data[date_str] = ["09:00", "10:00", "14:00", "15:00"]
            else:  # Odd days
                sample_data[date_str] = ["11:00", "13:00", "16:00"]
    
    return sample_data

def interactive_mode():
    """Interactive mode for adding custom timeslots."""
    print("📅 Interactive Timeslot Addition")
    print("=" * 40)
    
    timeslots_data = {}
    
    while True:
        print("\nEnter date and timeslots:")
        
        # Get date
        while True:
            date_input = input("Date (YYYY-MM-DD) or 'done' to finish: ").strip()
            
            if date_input.lower() == 'done':
                return timeslots_data
            
            try:
                # Validate date format
                datetime.strptime(date_input, "%Y-%m-%d")
                break
            except ValueError:
                print("❌ Invalid date format. Use YYYY-MM-DD")
        
        # Get timeslots
        print("Enter timeslots (HH:MM format, separated by commas):")
        print("Example: 09:00, 10:00, 14:00")
        
        while True:
            times_input = input("Timeslots: ").strip()
            
            if not times_input:
                print("❌ Please enter at least one timeslot")
                continue
            
            # Parse and validate times
            try:
                times = [t.strip() for t in times_input.split(",")]
                validated_times = []
                
                for time_str in times:
                    # Validate time format
                    datetime.strptime(time_str, "%H:%M")
                    validated_times.append(time_str)
                
                timeslots_data[date_input] = validated_times
                print(f"✅ Added: {date_input} -> {', '.join(validated_times)}")
                break
                
            except ValueError:
                print("❌ Invalid time format. Use HH:MM (24-hour format)")

def main():
    print("🚀 Mock Server Timeslot Manager")
    print("=" * 40)
    print("Make sure mock_server.py is running on localhost:5000")
    print()
    
    # Check server connection first
    try:
        response = requests.get("http://localhost:5000/api/timeslots", timeout=5)
        if response.status_code == 200:
            current_slots = response.json()
            total_slots = sum(len(slots) for slots in current_slots.values())
            print(f"📊 Current server status: {len(current_slots)} dates with {total_slots} total timeslots")
        else:
            print("⚠️  Server responded but API might not be working properly")
    except:
        print("❌ Cannot connect to mock server!")
        print("   Please start mock_server.py first, then run this script again.")
        return
    
    print("\nChoose an option:")
    print("1. Add sample data (next 7 weekdays)")
    print("2. Interactive mode (custom dates/times)")
    print("3. Quick add (single date)")
    print("4. View current timeslots")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        print("\n📅 Generating sample data...")
        sample_data = generate_sample_data()
        
        print("Sample data to add:")
        for date, times in sample_data.items():
            print(f"  {date}: {', '.join(times)}")
        
        confirm = input("\nAdd this data? (y/N): ").strip().lower()
        if confirm in ['y', 'yes']:
            add_timeslots(sample_data)
        else:
            print("❌ Cancelled")
    
    elif choice == "2":
        timeslots_data = interactive_mode()
        if timeslots_data:
            print(f"\n📋 Ready to add {len(timeslots_data)} dates:")
            for date, times in timeslots_data.items():
                print(f"  {date}: {', '.join(times)}")
            
            confirm = input("\nAdd these timeslots? (y/N): ").strip().lower()
            if confirm in ['y', 'yes']:
                add_timeslots(timeslots_data)
            else:
                print("❌ Cancelled")
        else:
            print("❌ No data to add")
    
    elif choice == "3":
        date = input("Enter date (YYYY-MM-DD): ").strip()
        times_input = input("Enter times (comma-separated, HH:MM): ").strip()
        
        try:
            # Validate date
            datetime.strptime(date, "%Y-%m-%d")
            
            # Validate and parse times
            times = [t.strip() for t in times_input.split(",")]
            for time_str in times:
                datetime.strptime(time_str, "%H:%M")
            
            timeslots_data = {date: times}
            add_timeslots(timeslots_data)
            
        except ValueError as e:
            print(f"❌ Invalid format: {str(e)}")
    
    elif choice == "4":
        try:
            response = requests.get("http://localhost:5000/api/timeslots", timeout=5)
            if response.status_code == 200:
                current_slots = response.json()
                print(f"\n📊 Current Timeslots ({len(current_slots)} dates):")
                for date, times in sorted(current_slots.items()):
                    if times:  # Only show dates with available slots
                        print(f"  {date}: {', '.join(times)}")
            else:
                print("❌ Failed to fetch current timeslots")
        except Exception as e:
            print(f"❌ Error fetching timeslots: {str(e)}")
    
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()