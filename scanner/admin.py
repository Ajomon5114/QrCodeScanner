from django.contrib import admin
from .models import User, AttendanceRecord

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'slno', 'name', 'church', 'seat_no', 'constituency', 'category')
    list_filter = ('church', 'constituency', 'category')
    search_fields = ('name', 'user_id', 'seat_no', 'slno')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'scan_time')
    list_filter = ('scan_time',)
