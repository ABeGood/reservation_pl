"""
Database testing utilities for Polish Card registration system.
Functions to load test data and verify database operations.
"""

import os
import logging
from typing import List, Optional
from models import load_registrants_from_json, Registrant
from database import DatabaseManager, add_new_registrant, batch_add_new_registrants, get_pending_registrations

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_mock_registrants_to_db(json_file_path: str = "mock_registrants.json") -> List[int]:
    """
    Load registrants from JSON file to database.
    
    Args:
        json_file_path (str): Path to JSON file with registrant data
        
    Returns:
        List[int]: List of created registrant IDs
        
    Raises:
        FileNotFoundError: If JSON file not found
        ValueError: If JSON data is invalid
        Exception: If database operation fails
    """
    print(f"🔄 Loading registrants from {json_file_path}...")
    
    try:
        # Load registrants from JSON
        registrants = load_registrants_from_json(json_file_path)
        print(f"📄 Loaded {len(registrants)} registrants from JSON")
        
        # Insert into database using batch function (preserves order)
        with DatabaseManager() as db:
            created_ids = db.batch_add_registrants(registrants)
        
        successful_inserts = len(created_ids)
        failed_inserts = len(registrants) - successful_inserts
        
        print(f"\n📊 Summary:")
        print(f"    ✅ Successfully inserted: {successful_inserts}")
        print(f"    ❌ Failed inserts: {failed_inserts}")
        print(f"    🆔 Created IDs: {created_ids}")
        print(f"    📋 Processing order: ID {min(created_ids) if created_ids else 'N/A'} will be processed first")
        
        return created_ids
        
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        raise
    except ValueError as e:
        print(f"❌ Invalid data: {e}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


def test_database_operations():
    """
    Test basic database operations.
    """
    print("\n🧪 Testing Database Operations")
    print("=" * 50)
    
    try:
        # Test connection
        print("1️⃣  Testing database connection...")
        with DatabaseManager() as db:
            stats = db.get_statistics()
            print(f"   ✅ Connection successful")
            print(f"   📊 Current registrants: {stats['general']['total_registrants']}")
            print(f"   ⏳ Pending: {stats['general']['pending_count']}")
            print(f"   ✅ Registered: {stats['general']['registered_count']}")
        
        # Test pending registrants retrieval
        print("\n2️⃣  Testing pending registrants retrieval...")
        pending = get_pending_registrations()
        print(f"   📋 Found {len(pending)} pending registrants")
        
        # Show some examples
        if pending:
            print("   Examples:")
            for registrant in pending[:3]:  # Show first 3
                print(f"   - {registrant}")
            if len(pending) > 3:
                print(f"   ... and {len(pending) - 3} more")
        
        # Test filtering by month
        print("\n3️⃣  Testing month filtering...")
        for month in [8, 9, 10]:
            month_pending = get_pending_registrations(month=month)
            month_name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][month-1]
            print(f"   📅 {month_name}: {len(month_pending)} pending registrants")
        
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        raise


def delete_tables():
    """
    Delete all tables from the database (registrants and reservations).
    
    WARNING: This will permanently delete ALL data in the database!
    """
    print("⚠️  WARNING: This will DELETE ALL TABLES and DATA!")
    confirm = input("Type 'DELETE ALL TABLES' to confirm: ").strip()
    
    if confirm != 'DELETE ALL TABLES':
        print("❌ Operation cancelled - confirmation text did not match")
        return False
    
    print("\n🗑️  Deleting all tables...")
    
    try:
        with DatabaseManager(auto_create_tables=False) as db:
            drop_tables_sql = """
            -- Drop tables in reverse order due to foreign key constraints
            DROP TABLE IF EXISTS registrants CASCADE;
            DROP TABLE IF EXISTS reservations CASCADE;
            """
            
            with db.connection.cursor() as cursor:
                cursor.execute(drop_tables_sql)
                db.connection.commit()
                
            print("✅ All tables deleted successfully")
            print("ℹ️  Tables will be recreated automatically on next database operation")
            return True
            
    except Exception as e:
        print(f"❌ Failed to delete tables: {e}")
        raise


def cleanup_test_data(registrant_ids: List[int]):
    """
    Clean up test data by removing registrants with given IDs.
    
    Args:
        registrant_ids (List[int]): List of registrant IDs to remove
    """
    print(f"\n🧹 Cleaning up {len(registrant_ids)} test registrants...")
    
    try:
        deleted_count = 0
        with DatabaseManager() as db:
            for registrant_id in registrant_ids:
                if db.delete_registrant(registrant_id):
                    deleted_count += 1
                    print(f"  🗑️  Deleted registrant ID: {registrant_id}")
                else:
                    print(f"  ⚠️  Registrant ID {registrant_id} not found")
        
        print(f"✅ Cleanup completed: {deleted_count}/{len(registrant_ids)} registrants deleted")
        
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        raise


def verify_json_format(json_file_path: str = "mock_registrants.json"):
    """
    Verify JSON file format and data validity.
    
    Args:
        json_file_path (str): Path to JSON file to verify
    """
    print(f"🔍 Verifying JSON file: {json_file_path}")
    print("=" * 50)
    
    try:
        registrants = load_registrants_from_json(json_file_path)
        
        print(f"✅ JSON format valid")
        print(f"📊 Found {len(registrants)} registrants")
        
        # Analyze data
        citizenships = {}
        application_types = {}
        months = {}
        
        for registrant in registrants:
            # Count citizenships
            citizenships[registrant.citizenship] = citizenships.get(registrant.citizenship, 0) + 1
            
            # Count application types
            app_type = registrant.application_type
            application_types[app_type] = application_types.get(app_type, 0) + 1
            
            # Count desired months
            month = registrant.desired_month
            months[month] = months.get(month, 0) + 1
        
        print(f"\n📈 Data Analysis:")
        print(f"   🌍 Citizenships:")
        for citizenship, count in citizenships.items():
            print(f"     - {citizenship}: {count}")
        
        print(f"   📝 Application types:")
        for app_type, count in application_types.items():
            print(f"     - {app_type}: {count}")
        
        print(f"   📅 Desired months:")
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        for month, count in sorted(months.items()):
            print(f"     - {month_names[month-1]}: {count}")
        
        # Show sample registrant
        if registrants:
            print(f"\n👤 Sample registrant:")
            sample = registrants[0]
            print(f"   Name: {sample.name} {sample.surname}")
            print(f"   Citizenship: {sample.citizenship}")
            print(f"   Email: {sample.email}")
            print(f"   Phone: {sample.phone}")
            print(f"   Application: {sample.application_type}")
            print(f"   Desired month: {sample.desired_month}")
        
    except Exception as e:
        print(f"❌ JSON verification failed: {e}")
        raise


def interactive_menu():
    """
    Interactive menu for database testing operations.
    """
    print("🚀 Database Test Suite - Interactive Mode")
    print("=" * 60)
    
    # Check environment setup
    if not os.getenv('DATABASE_URL'):
        print("⚠️  DATABASE_URL not found in environment")
        print("   Please add DATABASE_URL to your .env file")
        print("   Example: DATABASE_URL=postgresql://user:pass@host:port/dbname")
        return
    
    while True:
        print("\n📋 Available Operations:")
        print("1. 🔍 Verify JSON format")
        print("2. 🧪 Test database operations")
        print("3. 📄 Load mock registrants from JSON")
        print("4. 🧹 Clean up test data (by IDs)")
        print("5. 🗑️  DELETE ALL TABLES (DANGER!)")
        print("6. 🔄 Run full test suite")
        print("0. ❌ Exit")
        
        choice = input("\nSelect operation (0-6): ").strip()
        
        try:
            if choice == '0':
                print("👋 Goodbye!")
                break
            elif choice == '1':
                verify_json_format()
            elif choice == '2':
                test_database_operations()
            elif choice == '3':
                created_ids = load_mock_registrants_to_db()
                print(f"ℹ️  Created registrant IDs: {created_ids}")
            elif choice == '4':
                ids_input = input("Enter registrant IDs to delete (comma-separated): ").strip()
                if ids_input:
                    try:
                        ids = [int(x.strip()) for x in ids_input.split(',')]
                        cleanup_test_data(ids)
                    except ValueError:
                        print("❌ Invalid ID format. Please enter comma-separated numbers.")
                else:
                    print("❌ No IDs provided")
            elif choice == '5':
                delete_tables()
            elif choice == '6':
                main()
                break
            else:
                print("❌ Invalid choice. Please select 0-6.")
                
        except Exception as e:
            print(f"❌ Operation failed: {e}")
            continue


def main():
    """
    Main function to run full test suite.
    """
    print("🚀 Database Test Suite - Full Run")
    print("=" * 60)
    
    # Check environment setup
    if not os.getenv('DATABASE_URL'):
        print("⚠️  DATABASE_URL not found in environment")
        print("   Please add DATABASE_URL to your .env file")
        print("   Example: DATABASE_URL=postgresql://user:pass@host:port/dbname")
        return
    
    try:
        # Step 1: Verify JSON format
        verify_json_format()
        
        # Step 2: Test database operations
        test_database_operations()
        
        # Step 3: Load mock data
        print(f"\n" + "=" * 60)
        created_ids = load_mock_registrants_to_db()
        
        # Step 4: Test operations with new data
        print(f"\n" + "=" * 60)
        print("🔄 Re-testing with loaded data...")
        test_database_operations()
        
        # Step 5: Optional cleanup
        print(f"\n" + "=" * 60)
        cleanup_choice = input("🧹 Do you want to clean up test data? (y/N): ").strip().lower()
        if cleanup_choice in ['y', 'yes']:
            cleanup_test_data(created_ids)
        else:
            print("ℹ️  Test data kept in database")
            print(f"   Created registrant IDs: {created_ids}")
        
        print(f"\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"\n💥 Test suite failed: {e}")
        raise


if __name__ == "__main__":
    # Run interactive menu by default, or full test suite with --full argument
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        main()
    else:
        interactive_menu()