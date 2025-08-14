"""
Data models for Polish Card registration system.
Defines registrant data structure and validation.
"""

from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime
from enum import Enum


@dataclass
class Reservation:
    """
    Data model for a reservation in the Polish Card appointment system.
    
    Contains reservation details and appointment information.
    """
    # Primary identifier
    id: Optional[str] = None           # Reservation ID (will be expanded later)
    
    # Database fields (to be added later)
    # created_at: Optional[datetime] = None
    # appointment_date: Optional[str] = None
    # appointment_time: Optional[str] = None
    # timeslot_value: Optional[str] = None
    # status: Optional[str] = None
    # ... other reservation fields


class Citizenship(Enum):
    """Valid citizenship options from registration form."""
    BELARUS = "Białoruś"
    RUSSIA = "Rosja"
    UKRAINE = "Ukraina"
    STATELESS = "status bezpaństwowca"


class ApplicationType(Enum):
    """Valid application types from registration form."""
    ADULT = "osoba dorosła"
    ADULT_WITH_CHILDREN = "osoba dorosła i małoletnie dzieci"
    MINOR = "małoletni"


@dataclass
class Registrant:
    """
    Data model for a registrant in the Polish Card appointment system.
    
    Fields match the registration form structure with additional tracking fields.
    """
    # Form fields (from registration_page.html)
    name: str                           # imie - max 15 chars
    surname: str                        # nazwisko - max 20 chars  
    citizenship: str                    # obywatelstwo - from Citizenship enum
    email: str                          # email - valid email format
    phone: str                          # telefon - digits only
    application_type: str               # rodzaj_wizyty - from ApplicationType enum
    
    # Additional tracking fields
    desired_month: int                  # Month preference (1-12)
    reservation: Optional[str] = None   # Reservation ID if registered, None if pending
    
    # Database fields
    id: Optional[int] = None           # Primary key
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    registration_date: Optional[datetime] = None  # When successfully registered
    appointment_date: Optional[str] = None        # YYYY-MM-DD format
    appointment_time: Optional[str] = None        # HH:MM format
    timeslot_value: Optional[str] = None          # A1HH:MM or A2HH:MM format
    
    def __post_init__(self):
        """Validate data after initialization."""
        self.validate()
    
    def validate(self):
        """Validate registrant data against form constraints."""
        errors = []
        
        # Name validation
        if not self.name or len(self.name) > 15:
            errors.append("Name is required and must be max 15 characters")
        
        # Surname validation
        if not self.surname or len(self.surname) > 20:
            errors.append("Surname is required and must be max 20 characters")
        
        # Citizenship validation
        valid_citizenships = [c.value for c in Citizenship]
        if self.citizenship not in valid_citizenships:
            errors.append(f"Citizenship must be one of: {valid_citizenships}")
        
        # Email validation (basic)
        if not self.email or '@' not in self.email:
            errors.append("Valid email address is required")
        
        # Phone validation (digits only)
        if not self.phone or not self.phone.isdigit():
            errors.append("Phone number is required and must contain only digits")
        
        # Application type validation
        valid_app_types = [a.value for a in ApplicationType]
        if self.application_type not in valid_app_types:
            errors.append(f"Application type must be one of: {valid_app_types}")
        
        # Desired month validation
        if not (1 <= self.desired_month <= 12):
            errors.append("Desired month must be between 1 and 12")
        
        if errors:
            raise ValueError(f"Validation errors: {'; '.join(errors)}")
    
    def to_registration_data(self) -> dict:
        """
        Convert to format expected by send_registration_request().
        
        Returns:
            dict: Formatted data for registration request
        """
        return {
            'name': self.name,
            'surname': self.surname,
            'citizenship': self.citizenship,
            'email': self.email,
            'phone': self.phone,
            'application_type': self.application_type
        }
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Registrant':
        """Create Registrant from dictionary data."""
        return cls(**data)
    
    def set_reservation(self, reservation_id: str):
        """
        Set reservation ID when registration is successful.
        
        Args:
            reservation_id (str): ID of the created reservation
        """
        self.reservation = reservation_id
        self.registration_date = datetime.now()
        self.updated_at = datetime.now()
    
    def is_registered(self) -> bool:
        """Check if registrant has a reservation."""
        return self.reservation is not None
    
    def __str__(self) -> str:
        """String representation for logging and debugging."""
        status = f"✅ Registered (#{self.reservation})" if self.is_registered() else "⏳ Pending"
        appointment = f" - {self.appointment_date} at {self.appointment_time}" if self.appointment_date else ""
        return f"{self.name} {self.surname} ({self.citizenship}) - {status}{appointment}"
    
    def __repr__(self) -> str:
        """Developer representation."""
        return f"Registrant(id={self.id}, name='{self.name}', surname='{self.surname}', reservation={self.reservation})"


# Helper functions for creating registrants
def create_registrant(name: str, surname: str, citizenship: str, email: str, 
                     phone: str, application_type: str, desired_month: int) -> Registrant:
    """
    Create a new registrant with validation.
    
    Args:
        name: First name (max 15 chars)
        surname: Last name (max 20 chars)
        citizenship: Must be one of Citizenship enum values
        email: Valid email address
        phone: Phone number (digits only)
        application_type: Must be one of ApplicationType enum values
        desired_month: Preferred month (1-12)
    
    Returns:
        Registrant: Validated registrant object
        
    Raises:
        ValueError: If validation fails
    """
    return Registrant(
        name=name.strip(),
        surname=surname.strip(),
        citizenship=citizenship,
        email=email.strip().lower(),
        phone=phone.strip(),
        application_type=application_type,
        desired_month=desired_month,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


def get_citizenship_options() -> list:
    """Get list of valid citizenship options."""
    return [c.value for c in Citizenship]


def get_application_type_options() -> list:
    """Get list of valid application type options."""
    return [a.value for a in ApplicationType]