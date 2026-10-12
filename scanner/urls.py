from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('scanner/', views.index, name='scanner'),
    path('delegates/', views.delegates_list, name='delegates_list'),
    path('delegates/qr/<str:user_id>/', views.generate_single_qr, name='single_qr'),
    path('delegates/edit/<str:user_id>/', views.edit_delegate, name='edit_delegate'),
    path('delegates/delete/<str:user_id>/', views.delete_delegate, name='delete_delegate'),
    path('delegates/bulk_delete/', views.bulk_delete_delegates, name='bulk_delete_delegates'),
    path('delegates/export/csv/', views.export_csv, name='export_csv'),
    path('delegates/export/pdf/', views.export_delegates_pdf, name='export_delegates_pdf'),
    path('admin-upload/', views.admin_page, name='admin_page'),
    path('barcodes/', views.users_list, name='users_list'),
    path('barcodes/pdf/', views.generate_qr_pdf, name='generate_qr_pdf'),
    
    # API
    path('api/upload_users', views.upload_users, name='upload_users'),
    path('api/upload_images', views.upload_images, name='upload_images'),
    path('api/scan', views.scan_barcode, name='scan_barcode'),
    path('api/dashboard_data', views.api_dashboard_data, name='api_dashboard_data'),

    # Attendance Report
    path('attendance/', views.attendance_report, name='attendance_report'),
    path('attendance/mark/<str:user_id>/', views.mark_attendance, name='mark_attendance'),
    path('attendance/reset/<str:user_id>/', views.reset_attendance, name='reset_attendance'),
    path('attendance/reset_all/', views.reset_all_attendance, name='reset_all_attendance'),
    
    # System Users
    path('system-users/', views.system_users, name='system_users'),
    path('system-users/add/', views.add_system_user, name='add_system_user'),
    path('system-users/delete/<int:user_id>/', views.delete_system_user, name='delete_system_user'),
]

