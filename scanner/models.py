from django.db import models
from django.utils import timezone

class User(models.Model):
    user_id = models.CharField(max_length=50, primary_key=True)
    slno = models.CharField(max_length=50, null=True, blank=True)
    name = models.CharField(max_length=100)
    image_name = models.CharField(max_length=255, null=True, blank=True)
    church = models.CharField(max_length=100, null=True, blank=True)
    seat_no = models.CharField(max_length=50, null=True, blank=True)
    constituency = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name

class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    scan_time = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.name} - {self.scan_time}"
