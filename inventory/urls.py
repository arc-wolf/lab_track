from django.urls import path

from . import views

urlpatterns = [
    path("components/", views.student_dashboard, name="student_dashboard"),
    path("cart/", views.view_cart, name="view_cart"),
    path("cart/add/<int:component_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/remove/<int:item_id>/", views.remove_cart_item, name="remove_cart_item"),
    path("cart/generate/", views.generate_slip, name="generate_slip"),
    path("requests/", views.student_requests, name="student_requests"),
    # Admin inventory management
    path("admin/components/", views.admin_components, name="admin_components"),
    path("admin/components/new/", views.admin_component_create, name="admin_component_create"),
    path("admin/components/<int:pk>/edit/", views.admin_component_edit, name="admin_component_edit"),
    path("admin/components/<int:pk>/delete/", views.admin_component_delete, name="admin_component_delete"),
]
