from django.contrib import admin
from .models import GroupRemovalRequest, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)


@admin.register(GroupRemovalRequest)
class GroupRemovalRequestAdmin(admin.ModelAdmin):
    list_display = ("group", "member", "initiated_by", "status", "member_confirmed", "leader_confirmed", "created_at")
    list_filter = ("status", "initiated_by", "member_confirmed", "leader_confirmed")
