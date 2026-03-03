from django.contrib import admin

from .models import Component, Reservation


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_stock", "available_stock")
    search_fields = ("name", "category")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("user", "component", "quantity", "reserved_at", "expires_at", "is_active")
    list_filter = ("is_active", "reserved_at")
