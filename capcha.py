import requests
import base64
import os
from dotenv import load_dotenv


load_dotenv()
USER_ID = os.environ.get("USER_ID")
KEY = os.environ.get("KEY")

def solve(f):
    with open(f, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('ascii')
        url = 'https://api.apitruecaptcha.org/one/gettext'

        data = { 
            'userid':f'{USER_ID}', 
            'apikey':f'{KEY}',  
            'data':encoded_string
        }
        response = requests.post(url = url, json = data)
        data = response.json()
        return data
    
def solve_base64(base_64_capcha:str):
    url = 'https://api.apitruecaptcha.org/one/gettext'

    data = { 
        'userid':f'{USER_ID}', 
        'apikey':f'{KEY}',  
        'data':base_64_capcha
    }
    response = requests.post(url = url, json = data)
    data = response.json()
    return data
    
result = solve('cap_img/cap_4.png')
print(result['result'])