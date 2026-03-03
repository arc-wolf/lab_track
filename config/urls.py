from django.contrib import admin
from django.urls import path, include
from users.views import (
    LabTrackLoginView,
    dashboard_redirect,
    password_reset_confirm_otp,
    password_reset_request_otp,
    resend_password_reset_otp,
    resend_signup_otp,
    signup,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', LabTrackLoginView.as_view(), name='login'),
    # Keep Django's legacy password_reset URL shape themed via OTP page as well.
    path('accounts/password_reset/', password_reset_request_otp, name='password_reset_legacy'),
    path('accounts/password-reset/', password_reset_request_otp, name='password_reset'),
    path('accounts/password-reset/verify/', password_reset_confirm_otp, name='password_reset_otp_confirm'),
    path('accounts/password-reset/resend-otp/', resend_password_reset_otp, name='resend_password_reset_otp'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/signup/', signup, name='signup'),
    path('accounts/signup/resend-otp/', resend_signup_otp, name='resend_signup_otp'),
    path('users/', include('users.urls')),
    path('', dashboard_redirect, name='dashboard'),
    path('inventory/', include('inventory.urls')),
    path('requests/', include('requests_app.urls')),
    path('notifications/', include('notifications.urls')),
    path('api/', include('api.urls')),
]
