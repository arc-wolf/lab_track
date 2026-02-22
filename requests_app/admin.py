from django.contrib import admin

from .models import BorrowRequest, BorrowRequestItem


class BorrowRequestItemInline(admin.TabularInline):
    model = BorrowRequestItem
    extra = 0


@admin.register(BorrowRequest)
class BorrowRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "student", "faculty", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("student__username", "faculty__username")
    inlines = [BorrowRequestItemInline]
