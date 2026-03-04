from django.urls import path

from . import views

urlpatterns = [
    # POST /api/auth/token/
    # Body(JSON): {"identity":"<username|email|full_name>","password":"<password>"}
    # Auth: none
    # Success: 200 -> {"token":"...","user":{...}}
    path('auth/token/', views.issue_token, name='api_issue_token'),

    # POST /api/auth/logout/
    # Headers: Authorization: Token <token>
    # Auth: token required
    # Success: 200 -> {"ok": true}
    path('auth/logout/', views.logout_token, name='api_logout_token'),

    # GET /api/me/
    # Headers: Authorization: Token <token>
    # Auth: token required
    # Success: 200 -> {"user":{id,username,email,full_name,role,group_id}}
    path('me/', views.me, name='api_me'),

    # GET /api/components/
    # Headers: Authorization: Token <token>
    # Auth: token required
    # Success: 200 -> {"components":[...]}
    path('components/', views.components, name='api_components'),

    # GET /api/requests/
    # Headers: Authorization: Token <token>
    # Auth: token required
    # Scope: admin=all recent, faculty=assigned, student=group/own
    # Success: 200 -> {"requests":[...]}
    path('requests/', views.borrow_requests, name='api_borrow_requests'),
]
