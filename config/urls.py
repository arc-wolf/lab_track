from django.contrib import admin
from django.urls import path, include
from users.views import dashboard_redirect, signup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/signup/', signup, name='signup'),
    path('users/', include('users.urls')),
    path('', dashboard_redirect, name='dashboard'),
    path('inventory/', include('inventory.urls')),
    path('requests/', include('requests_app.urls')),
    path('notifications/', include('notifications.urls')),
]
