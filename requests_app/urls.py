from django.urls import path

from . import views

urlpatterns = [
    path("faculty/", views.faculty_dashboard, name="faculty_dashboard"),
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/requests/", views.admin_requests_console, name="admin_requests_console"),
    path("admin/request-console/", views.admin_requests_console, name="admin_request_console"),
    path("admin/faculty-console/", views.admin_faculty_console, name="admin_faculty_console"),
    path("admin/component-console/", views.admin_component_console, name="admin_component_console"),
    path("admin/analytics/", views.admin_data_console, name="admin_analytics_console"),
    path("admin/data-console/", views.admin_data_console, name="admin_data_console"),
    path("admin/maintenance/", views.admin_maintenance_queue, name="admin_maintenance_console"),
    path("admin/maintenance-queue/", views.admin_maintenance_queue, name="admin_maintenance_queue"),
    path("admin/reports-console/", views.admin_reports_console, name="admin_reports_console"),
    path("terminate/<int:request_id>/", views.terminate_slip, name="terminate_slip"),
    path("return/<int:request_id>/", views.mark_returned, name="mark_returned"),
    path("issue/<int:request_id>/", views.mark_issued, name="mark_issued"),
    path("penalty/<int:request_id>/", views.mark_penalty, name="mark_penalty"),
    path("approve/<int:request_id>/", views.approve_slip, name="approve_slip"),
    path("slip/<int:request_id>/pdf/", views.download_slip, name="download_slip"),
]
