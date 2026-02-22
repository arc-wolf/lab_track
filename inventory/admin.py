from django.contrib import admin

from .models import CartItem, Component


@admin.register(Component)
class ComponentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_stock", "available_stock")
    search_fields = ("name", "category")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("student", "component", "quantity", "added_at", "slip_generated")
    list_filter = ("slip_generated", "added_at")
