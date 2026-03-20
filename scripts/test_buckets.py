import httpx
import os
from dotenv import load_dotenv

load_dotenv()
url = os.getenv('SUPABASE_URL').rstrip('/') + '/storage/v1/bucket'
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
headers = {
    'apikey': key,
    'Authorization': f'Bearer {key}'
}
resp = httpx.get(url, headers=headers)
print('Status:', resp.status_code)
try:
    for b in resp.json():
        print(b['name'])
except Exception as e:
    print("Error:", e, resp.text)
