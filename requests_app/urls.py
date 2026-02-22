from django.urls import path

from . import views

urlpatterns = [
    path("faculty/", views.faculty_dashboard, name="faculty_dashboard"),
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("terminate/<int:request_id>/", views.terminate_slip, name="terminate_slip"),
    path("return/<int:request_id>/", views.mark_returned, name="mark_returned"),
    path("approve/<int:request_id>/", views.approve_slip, name="approve_slip"),
    path("slip/<int:request_id>/pdf/", views.download_slip, name="download_slip"),
]
