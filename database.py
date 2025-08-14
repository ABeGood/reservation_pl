"""
Database interaction module for Polish Card registration system.
Handles PostgreSQL operations for registrant data management.
"""

import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2 import sql
from dotenv import load_dotenv

from models import Registrant

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    PostgreSQL database manager for registrant data operations.
    
    Handles connection management, table creation, and CRUD operations.
    """
    
    def __init__(self):
        """Initialize database manager with connection from environment."""
        self.connection_string = os.getenv('DATABASE_URL')
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable not found")
        
        self.connection = None
        self._ensure_table_exists()
    
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(
                self.connection_string,
                cursor_factory=RealDictCursor
            )
            self.connection.autocommit = False
            logger.info("✅ Database connection established")
        except psycopg2.Error as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")
    
    def _ensure_connection(self):
        """Ensure active database connection."""
        if not self.connection or self.connection.closed:
            self.connect()
    
    def _ensure_table_exists(self):
        """Create registrants table if it doesn't exist."""
        self._ensure_connection()
        
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS registrants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(15) NOT NULL,
            surname VARCHAR(20) NOT NULL,
            citizenship VARCHAR(50) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            application_type VARCHAR(100) NOT NULL,
            desired_month INTEGER NOT NULL CHECK (desired_month BETWEEN 1 AND 12),
            registered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            registration_date TIMESTAMP NULL,
            appointment_date VARCHAR(10) NULL,
            appointment_time VARCHAR(5) NULL,
            timeslot_value VARCHAR(10) NULL,
            
            -- Constraints
            CONSTRAINT valid_citizenship CHECK (citizenship IN (
                'Białoruś', 'Rosja', 'Ukraina', 'status bezpaństwowca'
            )),
            CONSTRAINT valid_application_type CHECK (application_type IN (
                'osoba dorosła', 'osoba dorosła i małoletnie dzieci', 'małoletni'
            )),
            CONSTRAINT unique_email UNIQUE (email)
        );
        
        -- Create index on email for faster lookups
        CREATE INDEX IF NOT EXISTS idx_registrants_email ON registrants(email);
        
        -- Create index on registration status
        CREATE INDEX IF NOT EXISTS idx_registrants_registered ON registrants(registered);
        
        -- Create index on desired month for filtering
        CREATE INDEX IF NOT EXISTS idx_registrants_desired_month ON registrants(desired_month);
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_table_sql)
                self.connection.commit()
                logger.info("✅ Registrants table ready")
        except psycopg2.Error as e:
            logger.error(f"❌ Table creation failed: {e}")
            self.connection.rollback()
            raise
    
    def add_registrant(self, registrant: Registrant) -> int:
        """
        Add a new registrant to the database.
        
        Args:
            registrant (Registrant): Registrant object to add
            
        Returns:
            int: ID of the newly created registrant
            
        Raises:
            psycopg2.IntegrityError: If email already exists
            psycopg2.Error: For other database errors
        """
        self._ensure_connection()
        
        insert_sql = """
        INSERT INTO registrants (
            name, surname, citizenship, email, phone, application_type,
            desired_month, registered, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, (
                    registrant.name,
                    registrant.surname,
                    registrant.citizenship,
                    registrant.email,
                    registrant.phone,
                    registrant.application_type,
                    registrant.desired_month,
                    registrant.registered,
                    registrant.created_at or datetime.now(),
                    registrant.updated_at or datetime.now()
                ))
                
                registrant_id = cursor.fetchone()['id']
                self.connection.commit()
                
                logger.info(f"✅ Added registrant: {registrant.name} {registrant.surname} (ID: {registrant_id})")
                return registrant_id
                
        except psycopg2.IntegrityError as e:
            self.connection.rollback()
            if 'unique_email' in str(e):
                logger.error(f"❌ Email already exists: {registrant.email}")
                raise ValueError(f"Registrant with email {registrant.email} already exists")
            raise
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Failed to add registrant: {e}")
            raise
    
    def get_registrant_by_id(self, registrant_id: int) -> Optional[Registrant]:
        """
        Get registrant by ID.
        
        Args:
            registrant_id (int): Registrant ID
            
        Returns:
            Optional[Registrant]: Registrant object or None if not found
        """
        self._ensure_connection()
        
        select_sql = "SELECT * FROM registrants WHERE id = %s;"
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(select_sql, (registrant_id,))
                row = cursor.fetchone()
                
                if row:
                    return Registrant.from_dict(dict(row))
                return None
                
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to get registrant by ID {registrant_id}: {e}")
            raise
    
    def get_registrant_by_email(self, email: str) -> Optional[Registrant]:
        """
        Get registrant by email address.
        
        Args:
            email (str): Email address
            
        Returns:
            Optional[Registrant]: Registrant object or None if not found
        """
        self._ensure_connection()
        
        select_sql = "SELECT * FROM registrants WHERE email = %s;"
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(select_sql, (email.lower(),))
                row = cursor.fetchone()
                
                if row:
                    return Registrant.from_dict(dict(row))
                return None
                
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to get registrant by email {email}: {e}")
            raise
    
    def get_unregistered_registrants(self, desired_month: Optional[int] = None) -> List[Registrant]:
        """
        Get all unregistered registrants, optionally filtered by desired month.
        
        Args:
            desired_month (Optional[int]): Filter by desired month (1-12)
            
        Returns:
            List[Registrant]: List of unregistered registrants
        """
        self._ensure_connection()
        
        if desired_month:
            select_sql = """
            SELECT * FROM registrants 
            WHERE registered = FALSE AND desired_month = %s
            ORDER BY created_at ASC;
            """
            params = (desired_month,)
        else:
            select_sql = """
            SELECT * FROM registrants 
            WHERE registered = FALSE
            ORDER BY created_at ASC;
            """
            params = ()
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(select_sql, params)
                rows = cursor.fetchall()
                
                return [Registrant.from_dict(dict(row)) for row in rows]
                
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to get unregistered registrants: {e}")
            raise
    
    def update_registration_status(self, registrant_id: int, appointment_date: str, 
                                 appointment_time: str, timeslot_value: str) -> bool:
        """
        Mark registrant as successfully registered with appointment details.
        
        Args:
            registrant_id (int): Registrant ID
            appointment_date (str): Appointment date (YYYY-MM-DD)
            appointment_time (str): Appointment time (HH:MM)
            timeslot_value (str): Full timeslot value (A1HH:MM or A2HH:MM)
            
        Returns:
            bool: True if update successful, False if registrant not found
        """
        self._ensure_connection()
        
        update_sql = """
        UPDATE registrants 
        SET registered = TRUE,
            registration_date = %s,
            appointment_date = %s,
            appointment_time = %s,
            timeslot_value = %s,
            updated_at = %s
        WHERE id = %s;
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(update_sql, (
                    datetime.now(),
                    appointment_date,
                    appointment_time,
                    timeslot_value,
                    datetime.now(),
                    registrant_id
                ))
                
                updated = cursor.rowcount > 0
                self.connection.commit()
                
                if updated:
                    logger.info(f"✅ Updated registration status for registrant ID {registrant_id}")
                else:
                    logger.warning(f"⚠️  Registrant ID {registrant_id} not found for update")
                
                return updated
                
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Failed to update registration status: {e}")
            raise
    
    def delete_registrant(self, registrant_id: int) -> bool:
        """
        Delete a registrant from the database.
        
        Args:
            registrant_id (int): Registrant ID
            
        Returns:
            bool: True if deleted, False if not found
        """
        self._ensure_connection()
        
        delete_sql = "DELETE FROM registrants WHERE id = %s;"
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(delete_sql, (registrant_id,))
                
                deleted = cursor.rowcount > 0
                self.connection.commit()
                
                if deleted:
                    logger.info(f"✅ Deleted registrant ID {registrant_id}")
                else:
                    logger.warning(f"⚠️  Registrant ID {registrant_id} not found for deletion")
                
                return deleted
                
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Failed to delete registrant: {e}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registration statistics.
        
        Returns:
            Dict[str, Any]: Statistics including counts and breakdowns
        """
        self._ensure_connection()
        
        stats_sql = """
        SELECT 
            COUNT(*) as total_registrants,
            COUNT(*) FILTER (WHERE registered = TRUE) as registered_count,
            COUNT(*) FILTER (WHERE registered = FALSE) as pending_count,
            COUNT(DISTINCT citizenship) as unique_citizenships,
            COUNT(DISTINCT desired_month) as months_requested
        FROM registrants;
        """
        
        citizenship_sql = """
        SELECT citizenship, COUNT(*) as count, 
               COUNT(*) FILTER (WHERE registered = TRUE) as registered
        FROM registrants 
        GROUP BY citizenship 
        ORDER BY count DESC;
        """
        
        month_sql = """
        SELECT desired_month, COUNT(*) as count,
               COUNT(*) FILTER (WHERE registered = TRUE) as registered
        FROM registrants 
        GROUP BY desired_month 
        ORDER BY desired_month;
        """
        
        try:
            with self.connection.cursor() as cursor:
                # Get general stats
                cursor.execute(stats_sql)
                general_stats = dict(cursor.fetchone())
                
                # Get citizenship breakdown
                cursor.execute(citizenship_sql)
                citizenship_breakdown = [dict(row) for row in cursor.fetchall()]
                
                # Get month breakdown
                cursor.execute(month_sql)
                month_breakdown = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'general': general_stats,
                    'by_citizenship': citizenship_breakdown,
                    'by_month': month_breakdown,
                    'generated_at': datetime.now().isoformat()
                }
                
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to get statistics: {e}")
            raise
    
    def __enter__(self):
        """Context manager entry."""
        self._ensure_connection()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            if self.connection:
                self.connection.rollback()
        self.disconnect()


# Convenience functions for common operations
def add_new_registrant(name: str, surname: str, citizenship: str, email: str,
                      phone: str, application_type: str, desired_month: int) -> int:
    """
    Add a new registrant with validation and database storage.
    
    Returns:
        int: New registrant ID
    """
    from models import create_registrant
    
    registrant = create_registrant(
        name=name,
        surname=surname,
        citizenship=citizenship,
        email=email,
        phone=phone,
        application_type=application_type,
        desired_month=desired_month
    )
    
    with DatabaseManager() as db:
        return db.add_registrant(registrant)


def get_pending_registrations(month: Optional[int] = None) -> List[Registrant]:
    """
    Get all pending registrations, optionally for a specific month.
    
    Args:
        month (Optional[int]): Filter by desired month (1-12)
        
    Returns:
        List[Registrant]: Pending registrants
    """
    with DatabaseManager() as db:
        return db.get_unregistered_registrants(desired_month=month)


def mark_as_registered(registrant_id: int, appointment_date: str,
                      appointment_time: str, timeslot_value: str) -> bool:
    """
    Mark a registrant as successfully registered.
    
    Returns:
        bool: True if successful
    """
    with DatabaseManager() as db:
        return db.update_registration_status(
            registrant_id=registrant_id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            timeslot_value=timeslot_value
        )


if __name__ == "__main__":
    # Test database operations
    try:
        with DatabaseManager() as db:
            print("Database connection test successful!")
            stats = db.get_statistics()
            print(f"Current stats: {stats}")
    except Exception as e:
        print(f"Database test failed: {e}")