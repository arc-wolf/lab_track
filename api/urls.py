from django.urls import path

from . import views

urlpatterns = [
    path('auth/token/', views.issue_token, name='api_issue_token'),
    path('auth/logout/', views.logout_token, name='api_logout_token'),
    path('me/', views.me, name='api_me'),
    path('components/', views.components, name='api_components'),
    path('requests/', views.borrow_requests, name='api_borrow_requests'),
]
