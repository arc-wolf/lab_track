from django.urls import path
from . import views

urlpatterns = [
    path("student/group-console/", views.student_group_console, name="student_group_console"),
    path("student/profile-console/", views.student_profile_console, name="student_profile_console"),
    path("faculty/profile-console/", views.faculty_profile_console, name="faculty_profile_console"),
    path("groups/", views.faculty_groups, name="faculty_groups"),
    path("groups/<int:group_id>/approve/", views.group_approve, name="group_approve"),
    path("groups/<int:group_id>/reject/", views.group_reject, name="group_reject"),
    path("admin/groups/", views.admin_groups, name="admin_groups"),
    path("admin/groups/<int:group_id>/approve/", views.admin_group_approve, name="admin_group_approve"),
    path("admin/groups/<int:group_id>/reject/", views.admin_group_reject, name="admin_group_reject"),
    path("admin/student-console/", views.admin_student_console, name="admin_student_console"),
    path("admin/profile-console/", views.admin_profile_console, name="admin_profile_console"),
]
