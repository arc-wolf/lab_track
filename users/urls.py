from django.urls import path
from . import views

urlpatterns = [
    path("groups/", views.faculty_groups, name="faculty_groups"),
    path("groups/<int:group_id>/approve/", views.group_approve, name="group_approve"),
    path("groups/<int:group_id>/reject/", views.group_reject, name="group_reject"),
    path("admin/groups/", views.admin_groups, name="admin_groups"),
    path("admin/groups/<int:group_id>/approve/", views.admin_group_approve, name="admin_group_approve"),
    path("admin/groups/<int:group_id>/reject/", views.admin_group_reject, name="admin_group_reject"),
]
