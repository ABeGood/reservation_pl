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

from models import Registrant, Reservation

# Load environment variables
load_dotenv()

# Configure logging
from logging_config import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """
    PostgreSQL database manager for registrant data operations.
    
    Handles connection management, table creation, and CRUD operations.
    """
    
    def __init__(self, auto_create_tables=True):
        """Initialize database manager with connection from environment."""
        self.connection_string = os.getenv('DATABASE_URL')
        if not self.connection_string:
            raise ValueError("DATABASE_URL environment variable not found")
        
        self.connection = None
        if auto_create_tables:
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
        """Create registrants and reservations tables if they don't exist."""
        self._ensure_connection()
        
        create_tables_sql = """
        -- Create reservations table first (referenced by registrants)
        CREATE TABLE IF NOT EXISTS reservations (
            id VARCHAR(50) PRIMARY KEY,
            appointment_date DATE,
            appointment_time TIME,
            appointment_datetime TIMESTAMP WITHOUT TIME ZONE,
            room VARCHAR(100),
            registration_code VARCHAR(20),
            confirmed_name VARCHAR(50),
            confirmed_surname VARCHAR(50),
            confirmed_email VARCHAR(255),
            confirmed_phone VARCHAR(20),
            confirmed_citizenship VARCHAR(50),
            confirmed_application_type VARCHAR(100),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        
        -- Create registrants table
        CREATE TABLE IF NOT EXISTS registrants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(15) NOT NULL,
            surname VARCHAR(20) NOT NULL,
            citizenship VARCHAR(50) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            application_type VARCHAR(100) NOT NULL,
            desired_month INTEGER NOT NULL CHECK (desired_month BETWEEN 1 AND 12),
            reservation VARCHAR(50) NULL REFERENCES reservations(id),
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'UTC'),
            
            -- Constraints
            CONSTRAINT valid_citizenship CHECK (citizenship IN (
                'Białoruś', 'Rosja', 'Ukraina', 'status bezpaństwowca'
            )),
            CONSTRAINT valid_application_type CHECK (application_type IN (
                'osoba dorosła', 'osoba dorosła i małoletnie dzieci', 'małoletni'
            )),
            CONSTRAINT unique_email UNIQUE (email)
        );
        
        -- Create indexes for performance
        CREATE INDEX IF NOT EXISTS idx_registrants_email ON registrants(email);
        CREATE INDEX IF NOT EXISTS idx_registrants_reservation ON registrants(reservation);
        CREATE INDEX IF NOT EXISTS idx_registrants_desired_month ON registrants(desired_month);
        CREATE INDEX IF NOT EXISTS idx_registrants_reservation_null ON registrants(reservation) WHERE reservation IS NULL;
        
        -- Indexes for reservations table
        CREATE INDEX IF NOT EXISTS idx_reservations_appointment_date ON reservations(appointment_date);
        CREATE INDEX IF NOT EXISTS idx_reservations_registration_code ON reservations(registration_code);
        CREATE INDEX IF NOT EXISTS idx_reservations_confirmed_email ON reservations(confirmed_email);
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_tables_sql)
                self.connection.commit()
                logger.info("✅ Registrants and Reservations tables ready")
        except psycopg2.Error as e:
            logger.error(f"❌ Table creation failed: {e}")
            self.connection.rollback()
            raise
    
    def batch_add_registrants(self, registrants: List[Registrant]) -> List[int]:
        """
        Add multiple registrants in a specific order with transaction control.
        
        Args:
            registrants (List[Registrant]): List of registrants in desired processing order
            
        Returns:
            List[int]: List of created registrant IDs in the same order
            
        Raises:
            psycopg2.Error: For database errors (rolls back entire batch)
        """
        self._ensure_connection()
        
        insert_sql = """
        INSERT INTO registrants (
            name, surname, citizenship, email, phone, application_type,
            desired_month, reservation, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        
        created_ids = []
        successful_inserts = 0
        failed_inserts = 0
        
        try:
            with self.connection.cursor() as cursor:
                for i, registrant in enumerate(registrants, 1):
                    try:
                        cursor.execute(insert_sql, (
                            registrant.name,
                            registrant.surname,
                            registrant.citizenship.value,
                            registrant.email,
                            registrant.phone,
                            registrant.application_type.value,
                            registrant.desired_month,
                            registrant.reservation,
                            registrant.created_at or datetime.now(),
                            registrant.updated_at or datetime.now()
                        ))
                        
                        registrant_id = cursor.fetchone()['id']
                        created_ids.append(registrant_id)
                        successful_inserts += 1
                        logger.info(f"✅ {i}/{len(registrants)}: {registrant.name} {registrant.surname} (ID: {registrant_id})")
                        
                    except psycopg2.IntegrityError as e:
                        failed_inserts += 1
                        if 'unique_email' in str(e):
                            logger.error(f"❌ {i}/{len(registrants)}: {registrant.name} {registrant.surname} - Email already exists: {registrant.email}")
                            created_ids.append(None)  # Keep position for order tracking
                        else:
                            logger.error(f"❌ {i}/{len(registrants)}: {registrant.name} {registrant.surname} - Integrity error: {e}")
                            created_ids.append(None)
                    except psycopg2.Error as e:
                        failed_inserts += 1
                        logger.error(f"❌ {i}/{len(registrants)}: {registrant.name} {registrant.surname} - Database error: {e}")
                        created_ids.append(None)
                
                self.connection.commit()
                
                logger.info(f"📊 Batch insert summary: ✅ {successful_inserts} successful, ❌ {failed_inserts} failed")
                return [id for id in created_ids if id is not None]  # Return only successful IDs
                
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Batch insert failed: {e}")
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
            desired_month, reservation, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING id;
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, (
                    registrant.name,
                    registrant.surname,
                    registrant.citizenship.value,
                    registrant.email,
                    registrant.phone,
                    registrant.application_type.value,
                    registrant.desired_month,
                    registrant.reservation,
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
    
    def get_pending_registrants(self, desired_month: Optional[int] = None) -> List[Registrant]:
        """
        Get all pending registrants (without reservations), optionally filtered by desired month.
        
        Args:
            desired_month (Optional[int]): Filter by desired month (1-12)
            
        Returns:
            List[Registrant]: List of pending registrants
        """
        self._ensure_connection()
        
        if desired_month:
            select_sql = """
            SELECT * FROM registrants 
            WHERE reservation IS NULL AND desired_month = %s
            ORDER BY id ASC;
            """
            params = (desired_month,)
        else:
            select_sql = """
            SELECT * FROM registrants 
            WHERE reservation IS NULL
            ORDER BY id ASC;
            """
            params = ()
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(select_sql, params)
                rows = cursor.fetchall()
                
                return [Registrant.from_dict(dict(row)) for row in rows]
                
        except psycopg2.Error as e:
            logger.error(f"❌ Failed to get pending registrants: {e}")
            raise
    
    def create_reservation(self, reservation_id: str, success_data: Optional[dict] = None) -> bool:
        """
        Create a new reservation record with optional success data.
        
        Args:
            reservation_id (str): Unique reservation ID
            success_data (Optional[dict]): Success data from registration response
                Keys: appointment_date, appointment_time, appointment_datetime, room,
                      registration_code, name, surname, email, phone, citizenship, application_type
            
        Returns:
            bool: True if created successfully
        """
        self._ensure_connection()
        
        if success_data:
            # Parse datetime if provided as string (Polish timezone - no automatic conversion)
            appointment_datetime = None
            if success_data.get('appointment_datetime'):
                try:
                    # Parse as naive datetime and keep it naive (no timezone conversion)
                    naive_dt = datetime.strptime(
                        success_data['appointment_datetime'], 
                        '%Y-%m-%d %H:%M'
                    )
                    appointment_datetime = naive_dt
                except ValueError:
                    logger.warning(f"Invalid datetime format: {success_data['appointment_datetime']}")
            
            # Parse appointment_time if provided as string
            appointment_time = None
            if success_data.get('appointment_time'):
                try:
                    # Handle both HH:MM and H:MM formats
                    time_str = success_data['appointment_time'].strip()
                    if ':' in time_str:
                        appointment_time = datetime.strptime(time_str, '%H:%M').time()
                    else:
                        logger.warning(f"Time format missing colon: {time_str}")
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Invalid time format '{success_data.get('appointment_time')}': {e}")
            
            # Parse appointment_date if provided as string
            appointment_date = None
            if success_data.get('appointment_date'):
                try:
                    appointment_date = datetime.strptime(
                        success_data['appointment_date'], 
                        '%Y-%m-%d'
                    ).date()
                except ValueError:
                    logger.warning(f"Invalid date format: {success_data['appointment_date']}")
            
            insert_sql = """
            INSERT INTO reservations (
                id, appointment_date, appointment_time, appointment_datetime, room,
                registration_code, confirmed_name, confirmed_surname, confirmed_email,
                confirmed_phone, confirmed_citizenship, confirmed_application_type,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            );
            """
            
            params = (
                reservation_id,
                appointment_date,
                appointment_time,
                appointment_datetime,
                success_data.get('room'),
                success_data.get('registration_code'),
                success_data.get('name'),
                success_data.get('surname'),
                success_data.get('email'),
                success_data.get('phone'),
                success_data.get('citizenship'),
                success_data.get('application_type'),
                datetime.now(),
                datetime.now()
            )
        else:
            # Simple reservation creation (backward compatibility)
            insert_sql = "INSERT INTO reservations (id, created_at, updated_at) VALUES (%s, %s, %s);"
            params = (reservation_id, datetime.now(), datetime.now())
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, params)
                self.connection.commit()
                
                if success_data:
                    logger.info(f"✅ Created detailed reservation: {reservation_id} for {success_data.get('name', '')} {success_data.get('surname', '')}")
                else:
                    logger.info(f"✅ Created reservation: {reservation_id}")
                return True
                
        except psycopg2.IntegrityError:
            self.connection.rollback()
            logger.warning(f"⚠️  Reservation {reservation_id} already exists")
            return False
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Failed to create reservation: {e}")
            raise
    
    def assign_reservation_to_registrant(self, registrant_id: int, reservation_id: str) -> bool:
        """
        Assign a reservation to a registrant.
        
        Args:
            registrant_id (int): Registrant ID
            reservation_id (str): Reservation ID  
            
        Returns:
            bool: True if update successful, False if registrant not found
        """
        self._ensure_connection()
        
        # First ensure reservation exists
        self.create_reservation(reservation_id)
        
        update_sql = """
        UPDATE registrants 
        SET reservation = %s,
            updated_at = %s
        WHERE id = %s;
        """
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(update_sql, (
                    reservation_id,
                    datetime.now(),
                    registrant_id
                ))
                
                updated = cursor.rowcount > 0
                self.connection.commit()
                
                if updated:
                    logger.info(f"✅ Assigned reservation {reservation_id} to registrant ID {registrant_id}")
                else:
                    logger.warning(f"⚠️  Registrant ID {registrant_id} not found for reservation assignment")
                
                return updated
                
        except psycopg2.Error as e:
            self.connection.rollback()
            logger.error(f"❌ Failed to assign reservation: {e}")
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
            COUNT(*) FILTER (WHERE reservation IS NOT NULL) as registered_count,
            COUNT(*) FILTER (WHERE reservation IS NULL) as pending_count,
            COUNT(DISTINCT citizenship) as unique_citizenships,
            COUNT(DISTINCT desired_month) as months_requested
        FROM registrants;
        """
        
        citizenship_sql = """
        SELECT citizenship, COUNT(*) as count, 
               COUNT(*) FILTER (WHERE reservation IS NOT NULL) as registered
        FROM registrants 
        GROUP BY citizenship 
        ORDER BY count DESC;
        """
        
        month_sql = """
        SELECT desired_month, COUNT(*) as count,
               COUNT(*) FILTER (WHERE reservation IS NOT NULL) as registered
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
def batch_add_new_registrants(registrants_data: List[dict]) -> List[int]:
    """
    Add multiple registrants from a list of data dictionaries in specified order.
    
    Args:
        registrants_data (List[dict]): List of registrant data dicts in desired processing order
        
    Returns:
        List[int]: List of created registrant IDs
        
    Example:
        data = [
            {"name": "Jan", "surname": "Kowalski", "citizenship": "UKRAINE", ...},
            {"name": "Anna", "surname": "Smith", "citizenship": "RUSSIA", ...}
        ]
        ids = batch_add_new_registrants(data)  # Jan gets lower ID (processed first)
    """
    from models import create_registrant
    
    registrants = []
    for data in registrants_data:
        registrant = create_registrant(
            name=data['name'],
            surname=data['surname'],
            citizenship=data['citizenship'],
            email=data['email'],
            phone=data['phone'],
            application_type=data['application_type'],
            desired_month=data['desired_month']
        )
        registrants.append(registrant)
    
    with DatabaseManager() as db:
        return db.batch_add_registrants(registrants)


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
    Get all pending registrations (without reservations), optionally for a specific month.
    
    Args:
        month (Optional[int]): Filter by desired month (1-12)
        
    Returns:
        List[Registrant]: Pending registrants
    """
    with DatabaseManager() as db:
        return db.get_pending_registrants(desired_month=month)


def create_reservation_for_registrant(registrant_id: int, reservation_id: str, success_data: Optional[dict] = None) -> bool:
    """
    Create a reservation and assign it to a registrant.
    
    Args:
        registrant_id (int): Registrant ID
        reservation_id (str): Unique reservation ID
        success_data (Optional[dict]): Success data from registration response
        
    Returns:
        bool: True if successful
    """
    with DatabaseManager() as db:
        # Create reservation with success data
        if success_data:
            db.create_reservation(reservation_id, success_data)
        
        return db.assign_reservation_to_registrant(
            registrant_id=registrant_id,
            reservation_id=reservation_id
        )


# Backward compatibility alias
def mark_as_registered(registrant_id: int, appointment_date: str = None,
                      appointment_time: str = None, timeslot_value: str = None) -> bool:
    """
    Mark a registrant as successfully registered (legacy function).
    Creates a reservation ID automatically.
    
    Args:
        registrant_id (int): Registrant ID
        appointment_date (str, optional): Legacy parameter (ignored)
        appointment_time (str, optional): Legacy parameter (ignored)
        timeslot_value (str, optional): Legacy parameter (ignored)
        
    Returns:
        bool: True if successful
    """
    import uuid
    reservation_id = f"RES_{uuid.uuid4().hex[:8].upper()}"
    return create_reservation_for_registrant(
        registrant_id=registrant_id,
        reservation_id=reservation_id
    )


if __name__ == "__main__":
    # Test database operations
    try:
        with DatabaseManager() as db:
            logger.info("Database connection test successful!")
            stats = db.get_statistics()
            logger.info(f"Current stats: {stats}")
    except Exception as e:
        logger.error(f"Database test failed: {e}")