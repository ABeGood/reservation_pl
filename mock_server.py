#!/usr/bin/env python3
"""
Mock Registration Server for Polish Card Appointments
Replicates the functionality of https://olsztyn.uw.gov.pl/wizytakartapolaka/

This server provides all the necessary endpoints for testing:
- Main registration pages (pokoj_A1.php, pokoj_A2.php)
- Timeslots API endpoints (godziny_pokoj_A1.php, godziny_pokoj_A2.php)
- CAPTCHA generation (securimage/securimage_show.php)
- Form submission (send.php)
- Static assets (CSS, images)

Usage:
    python mock_server.py
    
Then point your test scripts to http://localhost:5000/
"""

from flask import Flask, request, render_template_string, send_file, session, jsonify
import random
import string
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import json
from datetime import datetime, timedelta
import re
import os

app = Flask(__name__)
app.secret_key = 'mock_server_secret_key_for_testing'

# Mock data storage
registrations = []
captcha_store = {}

# Available timeslots for different dates (simulated)
MOCK_TIMESLOTS = {
    "2025-06-16": ["09:00", "10:00", "11:00"],
    "2025-06-17": ["09:00", "10:00"],
    "2025-06-18": ["09:00", "11:00", "12:00"],
    "2025-06-19": ["10:00", "11:00"],
    "2025-06-20": ["09:00", "10:00", "11:00", "12:00"],
    "2025-06-23": ["09:00", "10:00"],
    "2025-06-24": ["11:00", "12:00"],
    "2025-06-25": [],  # No slots available
    "2025-06-26": ["09:00"],
    "2025-06-27": ["10:00", "11:00"],
    "2025-07-01": ["09:00", "10:00", "11:00"],
    "2025-07-02": ["09:00"],
    "2025-07-03": ["10:00", "11:00", "12:00"],
    "2025-07-04": ["09:00", "10:00"],
    "2025-07-07": ["09:00", "10:00", "11:00", "12:00"],
    "2025-07-08": ["09:00", "11:00"],
    "2025-07-09": ["09:00", "10:00"],
    "2025-07-10": ["09:00", "10:00", "11:00"],
    "2025-07-11": ["10:00", "11:00"],
    "2025-08-01": ["09:00", "10:00"],
    "2025-08-04": ["09:00", "11:00", "12:00"],
    "2025-08-05": ["10:00", "11:00"],
    "2025-08-06": ["09:00", "10:00", "11:00"],
    "2025-08-07": ["09:00"],
    "2025-08-08": ["10:00", "11:00", "12:00"],
}

def generate_captcha_text():
    """Generate random CAPTCHA text (6 characters)."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

def create_captcha_image(text):
    """Create CAPTCHA image with the given text."""
    # Create image
    width, height = 120, 40
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Try to use a basic font, fall back to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    # Add some noise
    for _ in range(50):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill='lightgray')
    
    # Draw text
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    draw.text((x, y), text, fill='black', font=font)
    
    # Add some distortion lines
    for _ in range(3):
        start = (random.randint(0, width), random.randint(0, height))
        end = (random.randint(0, width), random.randint(0, height))
        draw.line([start, end], fill='gray', width=1)
    
    return image

def generate_registration_code():
    """Generate a random registration code."""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

# HTML Templates
REGISTRATION_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <link href="style.css" rel="stylesheet" type="text/css">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.min.js"></script>
    <link rel="stylesheet" href="https://code.jquery.com/ui/1.12.1/themes/ui-lightness/jquery-ui.css">
    <title>Rezerwacja terminu wizyty w WMUW Karta Polaka</title>

    <script>
    var disabledDays = [
        "2025-03-25","2025-04-21","2025-05-01","2025-06-01","2025-06-02","2025-06-03",
        "2025-06-04","2025-06-05","2025-06-06","2025-06-07","2025-06-08","2025-06-09",
        "2025-06-10","2025-06-11","2025-06-12","2025-06-13","2025-06-14","2025-06-15",
        "2025-09-01","2025-09-02","2025-09-03","2025-09-04","2025-09-05","2025-09-06",
        "2025-06-21","2025-06-22","2025-06-28","2025-06-29","2025-07-05","2025-07-06",
        "2025-07-12","2025-07-13","2025-07-19","2025-07-20","2025-07-26","2025-07-27",
        "2025-08-02","2025-08-03","2025-08-09","2025-08-10","2025-08-16","2025-08-17",
        "2025-08-23","2025-08-24","2025-08-30","2025-08-31"
    ];

    function disableSpecificWeekDays(date) {
        if ((date.getDay() == 1) || (date.getDay() == 2) || (date.getDay() == 3) || (date.getDay() == 4) || (date.getDay() == 5)) {
            var string = jQuery.datepicker.formatDate('yy-mm-dd', date);
            return [disabledDays.indexOf(string) == -1];
        } else {
            return [false];
        }
    }

    $(function() {
        $("#datepicker").datepicker({
            minDate: new Date("2025/06/16"),
            maxDate: new Date("2025/08/31"),
            beforeShowDay: disableSpecificWeekDays,
        });
    });

    function postStuff() {
        var hr = new XMLHttpRequest();
        var url = "{{ timeslots_endpoint }}";
        var fn = document.getElementById("datepicker").value;
        var vars = "godzina=" + fn;
        hr.open("POST", url, true);
        hr.setRequestHeader("Content-type", "application/x-www-form-urlencoded");

        hr.onreadystatechange = function() {
            if(hr.readyState == 4 && hr.status == 200) {
                var return_data = hr.responseText;
                document.getElementById("class_godzina").innerHTML = return_data;
            }
        }

        hr.send(vars);
        document.getElementById("class_godzina").innerHTML = "processing...";
    }
    </script>
</head>

<body>
    <div class="tlo"><img src="graf/paszport.png"></div>
    <div class="tlo_white"></div>
    <div class="grafika"><a href="rezerwacje.php"><img src="graf/grafika.png" style="width:400px;height:80px;border:0;"></a></div>
    <div class="naglowek">
        <i style="position: absolute;top: 10px;left: 50px;">
            Wydział Spraw Obywatelskich i Cudzoziemców<br>
            Rezerwacja terminu wizyty
        </i>
    </div>
    <div class="pokoj_A_form">
        <span><i style="position: relative;top: 10px;">Przedłużenie ważności, wydanie duplikatu, zmiana danych Karty Polaka</i></span>
    </div>
    
    <div class="formularz" id="formularz">
        <form id="for_rezerwacji" action="send.php" method="POST" style="position: relative;">
            <fieldset id="personal">
                <label for="imie">Imię</label>
                <input type="text" name="imie" id="imie" maxlength="15" required autofocus placeholder="pole wymagane">
                
                <label for="nazwisko">Nazwisko</label>
                <input type="text" name="nazwisko" id="nazwisko" maxlength="20" required placeholder="pole wymagane">
                
                <label for="obywatelstwo">Obywatelstwo</label>					
                <select id="obywatel" name="obywatelstwo" maxlength="20" required placeholder="pole wymagane">
                    <option value="Białoruś">Białoruś</option>
                    <option value="Rosja">Rosja</option>
                    <option value="Ukraina">Ukraina</option>
                    <option value="status bezpaństwowca">status bezpaństwowca</option>
                </select>

                <label for="email">Adres e-mail</label>
                <input type="email" name="email" id="email" required placeholder="pole wymagane">
                
                <label for="telefon">Telefon</label>
                <input type="text" name="telefon" id="telefon" required placeholder="pole wymagane">
                
                <label for="rodzaj_wizyty">Kogo dotyczy wniosek</label>
                <select id="rodzaj" name="rodzaj_wizyty" maxlength="20" required placeholder="pole wymagane">
                    <option value="osoba dorosła">osoba dorosła</option>
                    <option value="osoba dorosła i małoletnie dzieci">osoba dorosła i małoletnie dzieci</option>
                    <option value="małoletni">małoletni</option>
                </select>
                
                <label for="datepicker">Data wizyty</label>
                <input type="text" name="datepicker" id="datepicker" required placeholder="pole wymagane" readonly onchange="postStuff();">
                
                <span><div id="class_godzina"></div></span>
            </fieldset>
            
            <span>
                <div id="class_data" class="data"></div>
                <label for="captcha_code">Przepisz kod z obrazka:</label>
                <div class="captcha">
                    <input type="text" size="10" maxlength="6" name="captcha_code" id="captcha_code">
                    <img style="float: left; padding-right: 5px" id="captcha_image" src="securimage/securimage_show.php" alt="CAPTCHA Image">
                    <a href="#" title="Zmień obraz" onclick="document.getElementById('captcha_image').src = 'securimage/securimage_show.php?' + Math.random(); this.blur(); return false">
                        <img height="32" width="32" src="graf/refresh.png" alt="Zmień obraz" style="border: 0px; vertical-align: bottom">
                    </a>
                </div>
                
                <input type="submit" value="Zatwierdź wizytę">	
            </span>
        </form>
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <link href="style.css" rel="stylesheet" type="text/css" />
</head>
<body>
    <table style='border: 1px solid black; width:340px'>
        <tr>
            <td>
                <center>
                    <img src="graf\\grafika.png" alt="Logo WMUW w Olsztynie" width="170" height="40" align="rightt">
                    <hr width="285" color="#545454"/>
                    Wydział Spraw Obywatelskich i Cudzoziemców<br />
                    Rezerwacja terminu wizyty - Obywatelstwo<br />
                    Przedłużenie ważności, wydanie duplikatu, zmiana danych Karty Polaka<br />
                    <hr width="285" color="#545454"/>
                </center>
                <p class="a">
                    Dane rejestracyjne:&nbsp<t class='text'>{{ name }} &nbsp {{ surname }}</t><br />
                    Adres e-mail-<t class='text'>&nbsp{{ email }}</t><br />
                    Telefon-<t class='text'>&nbsp{{ phone }}</t><br />
                    Data rezerwacji,godzina,stanowisko-<br>
                    <t class='text'>{{ appointment_date }} &nbsp {{ appointment_time }} &nbsp {{ room }}</t><br />
                    Obywatelstwo -<t class='text'>&nbsp{{ citizenship }}</t><br />
                    Dotyczy -<t class='text'>&nbsp{{ application_type }}</t><br />
                    Kod zgłoszenia-<t class='text'>&nbsp{{ registration_code }}</t><br />
                </p>
                <center>
                    <hr width="285" color="#545454"/>
                    <a href="#" onclick="javascript:window.print()">Drukuj | </a>
                    <a href='./rezerwacje.php'>Główna |</a>
                    <a href='./{{ back_page }}'>Wstecz</a><br />
                </center>
                <hr width="285" color="#545454"/>
            </td>
        </tr>
    </table>
</body>
</html>
"""

BAD_CAPTCHA_TEMPLATE = """
<html>
<head>
    <meta http-equiv="content-type" content="text/html; charset=utf-8" />
    <link href="style.css" rel="stylesheet" type="text/css" />
</head>
<body>
    <a href='./rezerwacje.php'>wstecz</a><br />
    kod z obrazka przepisany przez ciebie jest nieprawidłowy!!
</body>
</html>
"""

ERROR_TEMPLATE = """
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <link href="style.css" rel="stylesheet" type="text/css" />
</head>
<body>
    Błąd rezerwacji!! Sprawdź ponownie dostępność godzin dla wybranej daty.
    <a href='./rezerwacje.php'>Wstecz</a><br />
</body>
</html>
"""

CSS_CONTENT = """
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
    background-color: #f5f5f5;
}

.formularz {
    max-width: 600px;
    margin: 0 auto;
    background: white;
    padding: 20px;
    border-radius: 5px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

fieldset {
    border: none;
    padding: 0;
}

label {
    display: block;
    margin: 10px 0 5px 0;
    font-weight: bold;
}

input[type="text"], input[type="email"], select {
    width: 100%;
    padding: 8px;
    margin-bottom: 10px;
    border: 1px solid #ddd;
    border-radius: 3px;
    box-sizing: border-box;
}

input[type="submit"] {
    background-color: #007cba;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 3px;
    cursor: pointer;
    font-size: 16px;
    margin-top: 20px;
}

input[type="submit"]:hover {
    background-color: #005a87;
}

.captcha {
    margin: 10px 0;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 3px;
    background-color: #f9f9f9;
}

.captcha input {
    width: 100px;
    margin-right: 10px;
}

.grafika, .naglowek, .pokoj_A_form, .tlo, .tlo_white {
    /* Placeholder styles for layout elements */
}

table {
    margin: 20px auto;
    background: white;
    padding: 20px;
}

.text {
    font-weight: bold;
    color: #333;
}

.a {
    line-height: 1.6;
}

#class_godzina {
    margin: 10px 0;
    padding: 10px;
    background-color: #f0f0f0;
    border-radius: 3px;
}

.time-slot {
    display: inline-block;
    margin: 5px;
}

.time-slot input[type="radio"] {
    margin-right: 5px;
}

.time-slot label {
    display: inline;
    font-weight: normal;
    margin: 0;
    cursor: pointer;
}
"""

# Routes

@app.route('/')
def index():
    """Redirect to main registration page."""
    return '<h1>Mock Polish Card Registration Server</h1><p><a href="/pokoj_A1.php">Room A1</a> | <a href="/pokoj_A2.php">Room A2</a></p>'

@app.route('/pokoj_A1.php')
def room_a1():
    """Room A1 registration page."""
    return render_template_string(REGISTRATION_PAGE_TEMPLATE, timeslots_endpoint="godziny_pokoj_A1.php")

@app.route('/pokoj_A2.php')
def room_a2():
    """Room A2 registration page."""
    return render_template_string(REGISTRATION_PAGE_TEMPLATE, timeslots_endpoint="godziny_pokoj_A2.php")

@app.route('/godziny_pokoj_A1.php', methods=['POST'])
def timeslots_a1():
    """Get available timeslots for room A1."""
    return get_timeslots("A1")

@app.route('/godziny_pokoj_A2.php', methods=['POST'])
def timeslots_a2():
    """Get available timeslots for room A2."""
    return get_timeslots("A2")

def get_timeslots(room):
    """Generate timeslots HTML for given room and date."""
    date = request.form.get('godzina', '')
    
    if not date:
        return "Brak daty"
    
    # Get available slots for this date
    available_slots = MOCK_TIMESLOTS.get(date, [])
    
    if not available_slots:
        return f"Brak wolnych terminów na dzień {date}"
    
    # Generate HTML with radio buttons
    html = f"<p>Dostępne godziny na {date}:</p>"
    for slot in available_slots:
        timeslot_value = f"{room}{slot}"
        html += f'''
        <div class="time-slot">
            <input type="radio" name="godzina" id="{timeslot_value}" value="{timeslot_value}" required>
            <label for="{timeslot_value}">{slot}</label>
        </div>
        '''
    
    return html

@app.route('/securimage/securimage_show.php')
def captcha():
    """Generate and serve CAPTCHA image."""
    # Generate new CAPTCHA text
    captcha_text = generate_captcha_text()
    
    # Store in session
    session['captcha'] = captcha_text
    
    # Create image
    img = create_captcha_image(captcha_text)
    
    # Convert to bytes
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/send.php', methods=['POST'])
def submit_registration():
    """Handle registration form submission."""
    # Get form data
    name = request.form.get('imie', '').strip()
    surname = request.form.get('nazwisko', '').strip()
    citizenship = request.form.get('obywatelstwo', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('telefon', '').strip()
    application_type = request.form.get('rodzaj_wizyty', '').strip()
    date = request.form.get('datepicker', '').strip()
    timeslot = request.form.get('godzina', '').strip()
    captcha_input = request.form.get('captcha_code', '').strip()
    
    # Validate CAPTCHA
    expected_captcha = session.get('captcha', '')
    if captcha_input.lower() != expected_captcha.lower():
        return BAD_CAPTCHA_TEMPLATE
    
    # Validate required fields
    if not all([name, surname, citizenship, email, phone, application_type, date, timeslot]):
        return ERROR_TEMPLATE
    
    # Validate timeslot availability
    available_slots = MOCK_TIMESLOTS.get(date, [])
    
    # Extract time from timeslot (format: A1HH:MM or A2HH:MM)
    if len(timeslot) >= 4:
        room_id = timeslot[:2]  # A1 or A2
        time_part = timeslot[2:]  # HH:MM
    else:
        return ERROR_TEMPLATE
    
    if time_part not in available_slots:
        return ERROR_TEMPLATE
    
    # Generate registration code
    registration_code = generate_registration_code()
    
    # Determine room name
    room_name = f"{room_id} pokoj 25"
    
    # Determine back page
    back_page = f"pokoj_{room_id}.php"
    
    # Store registration
    registration_data = {
        'name': name,
        'surname': surname,
        'citizenship': citizenship,
        'email': email,
        'phone': phone,
        'application_type': application_type,
        'appointment_date': date,
        'appointment_time': time_part,
        'room': room_name,
        'registration_code': registration_code,
        'timestamp': datetime.now().isoformat()
    }
    
    registrations.append(registration_data)
    
    # Remove the booked slot from availability
    if date in MOCK_TIMESLOTS and time_part in MOCK_TIMESLOTS[date]:
        MOCK_TIMESLOTS[date].remove(time_part)
    
    # Clear session captcha
    session.pop('captcha', None)
    
    # Return success page
    return render_template_string(SUCCESS_TEMPLATE, 
                                name=name,
                                surname=surname,
                                email=email,
                                phone=phone,
                                appointment_date=date,
                                appointment_time=time_part,
                                room=room_name,
                                citizenship=citizenship,
                                application_type=application_type,
                                registration_code=registration_code,
                                back_page=back_page)

@app.route('/style.css')
def css():
    """Serve CSS file."""
    return CSS_CONTENT, 200, {'Content-Type': 'text/css'}

@app.route('/graf/<filename>')
def serve_graphics(filename):
    """Serve graphics files."""
    # For testing purposes, return a simple placeholder image
    if filename.endswith('.png'):
        # Create a simple placeholder image
        img = Image.new('RGB', (170, 40), color='lightblue')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "LOGO", fill='black')
        
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
    
    return "File not found", 404

@app.route('/rezerwacje.php')
def reservations():
    """Main reservations page."""
    return '<h1>Rezerwacje</h1><p><a href="/pokoj_A1.php">Pokój A1</a> | <a href="/pokoj_A2.php">Pokój A2</a></p>'

# API endpoints for testing
@app.route('/api/registrations')
def api_registrations():
    """Get all registrations (for testing)."""
    return jsonify(registrations)

@app.route('/api/timeslots')
def api_timeslots():
    """Get current timeslots status (for testing)."""
    return jsonify(MOCK_TIMESLOTS)

@app.route('/api/reset', methods=['POST'])
def api_reset():
    """Reset all data (for testing)."""
    global registrations
    registrations = []
    
    # Reset timeslots to original state
    global MOCK_TIMESLOTS
    MOCK_TIMESLOTS.update({
        "2025-06-16": ["09:00", "10:00", "11:00"],
        "2025-06-17": ["09:00", "10:00"],
        "2025-06-18": ["09:00", "11:00", "12:00"],
        "2025-06-19": ["10:00", "11:00"],
        "2025-06-20": ["09:00", "10:00", "11:00", "12:00"],
        "2025-06-23": ["09:00", "10:00"],
        "2025-06-24": ["11:00", "12:00"],
        "2025-06-25": [],
        "2025-06-26": ["09:00"],
        "2025-06-27": ["10:00", "11:00"],
        "2025-07-01": ["09:00", "10:00", "11:00"],
        "2025-07-02": ["09:00"],
        "2025-07-03": ["10:00", "11:00", "12:00"],
        "2025-07-04": ["09:00", "10:00"],
        "2025-07-07": ["09:00", "10:00", "11:00", "12:00"],
        "2025-07-08": ["09:00", "11:00"],
        "2025-07-09": ["09:00", "10:00"],
        "2025-07-10": ["09:00", "10:00", "11:00"],
        "2025-07-11": ["10:00", "11:00"],
    })
    
    return jsonify({"status": "reset", "message": "All data has been reset"})

if __name__ == '__main__':
    print("🚀 Starting Mock Polish Card Registration Server")
    print("📍 Server running at: http://localhost:5000")
    print("🏠 Main page: http://localhost:5000")
    print("🏢 Room A1: http://localhost:5000/pokoj_A1.php")
    print("🏢 Room A2: http://localhost:5000/pokoj_A2.php")
    print("🔧 API endpoints:")
    print("   - GET /api/registrations - View all registrations")
    print("   - GET /api/timeslots - View current timeslots")
    print("   - POST /api/reset - Reset all data")
    print("\nPress Ctrl+C to stop")
    
    app.run(debug=True, host='0.0.0.0', port=5000)