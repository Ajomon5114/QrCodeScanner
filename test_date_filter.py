import django
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from scanner.models import AttendanceRecord
from django.utils import timezone

try:
    today = timezone.localdate()
    res = AttendanceRecord.objects.filter(scan_time__date=today).exists()
    print("SUCCESS! Result:", res)
except Exception as e:
    print("ERROR:", str(e))
