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
    # Success: 200 -> {"user":{id,username,email,full_name,role,group_id,email_locked}}
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

    # GET /api/admin/overview/
    # Headers: Authorization: Token <token>
    # Auth: token required + admin role
    # Success: 200 -> admin dashboard glimpse payload
    path('admin/overview/', views.admin_overview, name='api_admin_overview'),

    # GET /api/admin/console-map/
    # Headers: Authorization: Token <token>
    # Auth: token required + admin role
    # Success: 200 -> web console route map for admin navigation
    path('admin/console-map/', views.admin_console_map, name='api_admin_console_map'),

    # GET /api/admin/policy/
    # Headers: Authorization: Token <token>
    # Auth: token required + admin role
    # Success: 200 -> global LabPolicy values
    path('admin/policy/', views.admin_policy, name='api_admin_policy'),

    # POST /api/admin/policy/update/
    # Headers: Authorization: Token <token>
    # Auth: token required + admin role
    # Body: any subset of policy fields
    path('admin/policy/update/', views.admin_update_policy, name='api_admin_update_policy'),

    # POST /api/admin/components/<id>/fines/
    # Headers: Authorization: Token <token>
    # Auth: token required + admin role
    # Body: fine_per_day/fine_damaged/fine_missing_parts/fine_not_working (int or null)
    path('admin/components/<int:component_id>/fines/', views.admin_update_component_fines, name='api_admin_update_component_fines'),
]
