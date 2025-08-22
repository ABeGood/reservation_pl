#!/usr/bin/env python3
"""
Test script for running the realtime availability monitor against the mock server.
Make sure mock_server.py is running on localhost:5000 before running this script.
"""

from realtime_availability_monitor import RealTimeAvailabilityMonitor
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    print("Real-time Monitor Testing with Mock Server")
    print("==========================================")
    print("Make sure mock_server.py is running on localhost:5000")
    print()
    
    # Choose room
    print("Select room to monitor:")
    print("1. Room A1 (default)")
    print("2. Room A2")
    
    choice = input("Enter choice (1 or 2, default=1): ").strip()
    
    if choice == "2":
        page_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A2.php"
    else:
        page_url = "https://olsztyn.uw.gov.pl/wizytakartapolaka/pokoj_A1.php"
    
    # Create monitor with mock server flag
    monitor = RealTimeAvailabilityMonitor(page_url=page_url, use_mock_server=True)
    
    print(f"🎯 Monitoring: {monitor.page_url}")
    print(f"🔗 Base URL: {monitor.base_url}")
    print(f"📡 Endpoint: {monitor.endpoint}")
    print()
    
    # Ask for monitoring duration
    try:
        duration_input = input("Enter monitoring duration in minutes (or press Enter for indefinite): ").strip()
        max_duration = int(duration_input) if duration_input else None
    except ValueError:
        max_duration = None
    
    # Ask about auto-registration
    auto_reg_input = input("Enable auto-registration? (y/N): ").strip().lower()
    auto_registration = auto_reg_input in ['y', 'yes']
    
    print()
    print("🚀 Starting monitor...")
    print("📝 Note: This will work with mock server data only")
    print("Press Ctrl+C to stop")
    print()
    
    # Start monitoring
    monitor.start_monitoring(
        max_duration_minutes=max_duration,
        check_interval=2.0,  # Slower for testing
        auto_registration=auto_registration
    )

if __name__ == "__main__":
    main()