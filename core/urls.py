from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('scanner.urls')),
]
