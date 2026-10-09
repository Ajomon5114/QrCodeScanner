import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User as AuthUser, Group

# Create Groups
viewer_group, _ = Group.objects.get_or_create(name='Viewer')
admin_group, _ = Group.objects.get_or_create(name='Admin')

# Create Superuser
if not AuthUser.objects.filter(username='superadmin').exists():
    AuthUser.objects.create_superuser('superadmin', 'admin@example.com', 'admin123')
    print("Superuser 'superadmin' created with password 'admin123'")
