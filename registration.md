# Polish Card Registration Process Documentation

## Overview
This document describes the registration process for Polish Card appointments at the Olsztyn office. The process involves filling out a form, selecting a date and time slot, solving a CAPTCHA, and submitting the reservation request.

## Registration Form Structure

### Form Element
- **Form ID**: `for_rezerwacji`
- **Action URL**: `send.php`
- **Method**: POST
- **Progress Tracking**: Uses progression.js for step-by-step guidance

### Required Form Fields

1. **Personal Information**:
   - `imie` (Name) - Text input, maxlength 15, required
   - `nazwisko` (Surname) - Text input, maxlength 20, required
   - `obywatelstwo` (Citizenship) - Select dropdown with options:
     - Białoruś (Belarus)
     - Rosja (Russia)
     - Ukraina (Ukraine)
     - status bezpaństwowca (stateless person status)

2. **Contact Information**:
   - `email` - Email input, required
   - `telefon` (Phone) - Text input with numeric validation, required

3. **Application Type**:
   - `rodzaj_wizyty` (Visit type) - Select dropdown with options:
     - osoba dorosła (adult person)
     - osoba dorosła i małoletnie dzieci (adult and minor children)
     - małoletni (minor)

### Date and Time Selection Process

#### Date Selection
- **Field**: `datepicker` (readonly input)
- **JavaScript Configuration**:
  - Uses jQuery UI datepicker
  - Min date: 2025/06/16
  - Max date: 2025/08/31
  - Disabled days: Extensive array of blocked dates including holidays and weekends
  - Only weekdays (Monday-Friday) are selectable
  - `onchange` event triggers `postStuff()` function

#### Time Slot Selection
- **Container**: `class_godzina` div
- **Dynamic Loading**: Time slots are fetched via AJAX when date is selected
- **AJAX Call Details**:
  - Endpoint: `godziny_pokoj_A2.php` (for Room A2)
  - Method: POST
  - Parameter: `godzina` = selected date value
  - Response: HTML content with radio buttons for available time slots

#### Time Slot Format
- **Example from HTML**: `<input type="radio" id="A209:00" name="godzina" value="A209:00">`
- **Pattern**: Room identifier (A2) + time (09:00)
- **Selection**: Single radio button selection required

### CAPTCHA Integration

#### CAPTCHA Display
- **Image Source**: `securimage/securimage_show.php?[random_parameter]`
- **Input Field**: `captcha_code` - Text input, maxlength 6
- **Refresh Functionality**: Click to generate new CAPTCHA image
- **Refresh URL**: Updates with `Math.random()` parameter to prevent caching

#### CAPTCHA Requirements
- 6-character maximum input
- Required field for form submission
- Case-sensitive validation (server-side)

## Form Submission Process

### Submission Flow
1. **Form Validation**: All required fields must be filled
2. **Date Selection**: Valid date must be chosen from datepicker
3. **Time Slot Selection**: One time slot radio button must be selected
4. **CAPTCHA Solution**: Correct CAPTCHA code must be entered
5. **Form Submission**: POST request to `send.php`

### Form Data Structure
When submitted, the form sends the following data:
```
imie: [user_name]
nazwisko: [user_surname]
obywatelstwo: [selected_citizenship]
email: [user_email]
telefon: [user_phone]
rodzaj_wizyty: [application_type]
datepicker: [selected_date]
godzina: [selected_timeslot] (format: A2HH:MM)
captcha_code: [solved_captcha]
```

### Session Management
- **Session Cookie**: PHPSESSID required for form submission
- **Session Initialization**: Must visit CAPTCHA endpoint first to establish session
- **Session Persistence**: Maintained throughout the form filling and submission process

## Progressive Enhancement Features

### Form Progress Tracking
- **Library**: progression.js
- **Visual Elements**:
  - Progress bar showing completion percentage
  - Step-by-step tooltips
  - Real-time validation feedback
- **Configuration**:
  - Tooltip position: right
  - Progress bar colors: blue gradient
  - Animated transitions

### User Experience Elements
- **Field Validation**: Real-time validation with visual feedback
- **Helper Text**: Context-sensitive help for each field
- **Progress Indication**: Shows user completion status (e.g., "7/8" steps)
- **Error Prevention**: Readonly date field prevents manual entry

## Technical Implementation Notes

### JavaScript Dependencies
- jQuery 1.10.2
- jQuery UI 1.10.4 (for datepicker)
- progression.js (for form progress tracking)

### Date Handling
- **Format**: YYYY-MM-DD for internal processing
- **Display**: Localized Polish format in UI
- **Validation**: Server-side validation against disabled days array

### AJAX Time Slot Loading
- **Loading State**: Shows "processing..." during AJAX request
- **Error Handling**: Basic XMLHttpRequest status checking
- **Content Replacement**: Direct innerHTML replacement of time slot container

### Anti-Automation Measures
- CAPTCHA requirement for all submissions
- Session-based validation
- Readonly date field requires JavaScript interaction
- Dynamic time slot loading prevents pre-filling

## Integration Points

### API Endpoints
- **Time Slots**: `godziny_pokoj_A2.php` (POST with date parameter)
- **Form Submission**: `send.php` (POST with all form data)
- **CAPTCHA Image**: `securimage/securimage_show.php`

### External Dependencies
- **CAPTCHA Service**: Uses Securimage library for CAPTCHA generation
- **Email System**: Confirmation emails sent to provided email address
- **Database**: Appointment storage and conflict checking

## Error Handling
- **Client-side**: HTML5 form validation for required fields
- **Server-side**: CAPTCHA validation and appointment conflict checking
- **User Feedback**: Progress indicators and helper text guide user through process