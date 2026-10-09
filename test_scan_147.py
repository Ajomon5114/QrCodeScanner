import urllib.request
import json
import sqlite3

# Let's hit the endpoint but with a real user!
data = json.dumps({'user_id': '147'}).encode('utf-8')
req = urllib.request.Request('http://127.0.0.1:8000/api/scan', data=data, headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req) as response:
        print("STATUS:", response.status)
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code)
    print(e.read().decode('utf-8'))
except Exception as e:
    print("OTHER ERROR:", e)
