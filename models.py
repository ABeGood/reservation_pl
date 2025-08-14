"""
Data models for Polish Card registration system.
Defines registrant data structure and validation.
"""

from dataclasses import dataclass, asdict
from typing import Optional, List
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
    citizenship: Citizenship            # obywatelstwo - from Citizenship enum
    email: str                          # email - valid email format
    phone: str                          # telefon - digits only
    application_type: ApplicationType   # rodzaj_wizyty - from ApplicationType enum
    
    # Additional tracking fields
    desired_month: int                  # Month preference (1-12)
    reservation: Optional[str] = None   # Reservation ID if registered, None if pending
    
    # Database fields
    id: Optional[int] = None           # Primary key
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
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
        if not isinstance(self.citizenship, Citizenship):
            errors.append(f"Citizenship must be a Citizenship enum, got: {type(self.citizenship)}")
        
        # Email validation (basic)
        if not self.email or '@' not in self.email:
            errors.append("Valid email address is required")
        
        # Phone validation (digits only)
        if not self.phone or not self.phone.isdigit():
            errors.append("Phone number is required and must contain only digits")
        
        # Application type validation
        if not isinstance(self.application_type, ApplicationType):
            errors.append(f"Application type must be an ApplicationType enum, got: {type(self.application_type)}")
        
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
            'citizenship': self.citizenship.value,
            'email': self.email,
            'phone': self.phone,
            'application_type': self.application_type.value
        }
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database operations."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Registrant':
        """Create Registrant from dictionary data."""
        # Convert string values to enums if needed
        if 'citizenship' in data and isinstance(data['citizenship'], str):
            citizenship_str = data['citizenship']
            # Try enum key first (e.g., "UKRAINE")
            try:
                data['citizenship'] = Citizenship[citizenship_str]
            except KeyError:
                # Try enum value (e.g., "Ukraina")
                for citizenship in Citizenship:
                    if citizenship.value == citizenship_str:
                        data['citizenship'] = citizenship
                        break
        
        if 'application_type' in data and isinstance(data['application_type'], str):
            app_type_str = data['application_type']
            # Try enum key first (e.g., "ADULT")
            try:
                data['application_type'] = ApplicationType[app_type_str]
            except KeyError:
                # Try enum value (e.g., "osoba dorosła")
                for app_type in ApplicationType:
                    if app_type.value == app_type_str:
                        data['application_type'] = app_type
                        break
        
        return cls(**data)
    
    def set_reservation(self, reservation_id: str):
        """
        Set reservation ID when registration is successful.
        
        Args:
            reservation_id (str): ID of the created reservation
        """
        self.reservation = reservation_id
        self.updated_at = datetime.now()
    
    def is_registered(self) -> bool:
        """Check if registrant has a reservation."""
        return self.reservation is not None
    
    def __str__(self) -> str:
        """String representation for logging and debugging."""
        status = f"✅ Registered (#{self.reservation})" if self.is_registered() else "⏳ Pending"
        return f"{self.name} {self.surname} ({self.citizenship.value}) - {status}"
    
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
        citizenship: Citizenship string value or Citizenship enum
        email: Valid email address
        phone: Phone number (digits only)
        application_type: ApplicationType string value or ApplicationType enum
        desired_month: Preferred month (1-12)
    
    Returns:
        Registrant: Validated registrant object
        
    Raises:
        ValueError: If validation fails
    """
    # Convert string values to enums
    if isinstance(citizenship, str):
        citizenship_enum = None
        # Try enum key first (e.g., "UKRAINE")
        try:
            citizenship_enum = Citizenship[citizenship]
        except KeyError:
            # Try enum value (e.g., "Ukraina")
            for c in Citizenship:
                if c.value == citizenship:
                    citizenship_enum = c
                    break
        
        if citizenship_enum is None:
            valid_keys = [c.name for c in Citizenship]
            valid_values = [c.value for c in Citizenship]
            raise ValueError(f"Invalid citizenship: {citizenship}. Must be one of keys: {valid_keys} or values: {valid_values}")
        citizenship = citizenship_enum
    
    if isinstance(application_type, str):
        app_type_enum = None
        # Try enum key first (e.g., "ADULT")
        try:
            app_type_enum = ApplicationType[application_type]
        except KeyError:
            # Try enum value (e.g., "osoba dorosła")
            for a in ApplicationType:
                if a.value == application_type:
                    app_type_enum = a
                    break
        
        if app_type_enum is None:
            valid_keys = [a.name for a in ApplicationType]
            valid_values = [a.value for a in ApplicationType]
            raise ValueError(f"Invalid application type: {application_type}. Must be one of keys: {valid_keys} or values: {valid_values}")
        application_type = app_type_enum
    
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


def load_registrants_from_json(file_path: str) -> List[Registrant]:
    """
    Load registrants from a JSON file.
    
    Args:
        file_path (str): Path to the JSON file
        
    Returns:
        List[Registrant]: List of validated registrant objects
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If JSON is invalid or registrant data is invalid
        
    JSON Format:
    [
        {
            "name": "Jan",
            "surname": "Kowalski",
            "citizenship": "UKRAINE",  // or "Ukraina"
            "email": "jan.kowalski@example.com",
            "phone": "123456789",
            "application_type": "ADULT",  // or "osoba dorosła"
            "desired_month": 8
        },
        ...
    ]
    
    Note: citizenship and application_type can use either:
    - Enum keys: "UKRAINE", "RUSSIA", "BELARUS", "STATELESS" / "ADULT", "ADULT_WITH_CHILDREN", "MINOR"
    - Polish values: "Ukraina", "Rosja", "Białoruś", "status bezpaństwowca" / "osoba dorosła", etc.
    """
    import json
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            raise ValueError("JSON file must contain an array of registrant objects")
        
        registrants = []
        for i, registrant_data in enumerate(data):
            try:
                # Create registrant with validation
                registrant = create_registrant(
                    name=registrant_data['name'],
                    surname=registrant_data['surname'],
                    citizenship=registrant_data['citizenship'],
                    email=registrant_data['email'],
                    phone=registrant_data['phone'],
                    application_type=registrant_data['application_type'],
                    desired_month=registrant_data['desired_month']
                )
                registrants.append(registrant)
            except KeyError as e:
                raise ValueError(f"Missing required field {e} in registrant {i+1}")
            except ValueError as e:
                raise ValueError(f"Invalid data in registrant {i+1}: {e}")
        
        return registrants
        
    except FileNotFoundError:
        raise FileNotFoundError(f"JSON file not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")


def save_registrants_to_json(registrants: List[Registrant], file_path: str) -> None:
    """
    Save registrants to a JSON file.
    
    Args:
        registrants (List[Registrant]): List of registrants to save
        file_path (str): Path to the output JSON file
    """
    import json
    
    data = []
    for registrant in registrants:
        data.append({
            "name": registrant.name,
            "surname": registrant.surname,
            "citizenship": registrant.citizenship.value,
            "email": registrant.email,
            "phone": registrant.phone,
            "application_type": registrant.application_type.value,
            "desired_month": registrant.desired_month
        })
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)