from django.contrib import admin

from .models import BorrowRequest, BorrowItem, BorrowAction


class BorrowRequestItemInline(admin.TabularInline):
    model = BorrowItem
    extra = 0


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "faculty", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__username", "faculty__username")
    inlines = [BorrowRequestItemInline]


@admin.register(BorrowAction)
class BorrowActionAdmin(admin.ModelAdmin):
    list_display = ("borrow_request", "action", "performed_by", "timestamp")
    list_filter = ("action", "timestamp")
    search_fields = ("borrow_request__id", "performed_by__username")
