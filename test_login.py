import urllib.request
import urllib.parse
import json
import http.cookiejar

# Create a cookie jar to store session cookies
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Login
# Need to get CSRF token first
resp = opener.open('http://127.0.0.1:8000/accounts/login/')
html = resp.read().decode('utf-8')

csrf_token = None
for cookie in cj:
    if cookie.name == 'csrftoken':
        csrf_token = cookie.value

if not csrf_token:
    print("Could not get CSRF token")
    exit()

# We need a superuser account. The previous tasks probably had an admin. Let's try 'admin' / 'admin' or just skip login and temporarily remove the @user_passes_test decorator in views.py!

