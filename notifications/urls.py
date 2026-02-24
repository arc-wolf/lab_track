from django.urls import path
from . import views

urlpatterns = [
    path("", views.notifications_center, name="notifications"),
]
