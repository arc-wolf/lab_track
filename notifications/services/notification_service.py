from datetime import date
from typing import Any, Dict
from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from inventory.models import Component
from requests_app.models import BorrowRequest
from users.models import Group, Profile


def get_admin_notifications() -> Dict[str, QuerySet]:
    """Retrieve system alerts and notification queries for Admin users."""
    low_stock = Component.objects.filter(available_stock__lte=2).order_by("available_stock", "name")
    pending = BorrowRequest.objects.filter(status=BorrowRequest.STATUS_PENDING).order_by("-created_at")
    due_today = BorrowRequest.objects.filter(
        status=BorrowRequest.STATUS_APPROVED, due_date=date.today()
    ).select_related("user", "faculty")
    return {
        "low_stock": low_stock,
        "pending": pending,
        "due_today": due_today,
    }


def get_faculty_notifications(faculty_user: User) -> Dict[str, QuerySet]:
    """Retrieve assigned group requests, pending slips, and due today slips for Faculty users."""
    full_name = getattr(getattr(faculty_user, "profile", None), "full_name", "")
    Group.objects.filter(faculty__isnull=True).filter(
        Q(members__user__profile__faculty_incharge=faculty_user.username)
        | Q(members__user__profile__faculty_incharge=faculty_user.email)
        | Q(members__user__profile__faculty_incharge=full_name)
    ).update(faculty=faculty_user)

    my_group_requests = (
        Group.objects.filter(faculty=faculty_user, status=Group.STATUS_PENDING)
        .prefetch_related("members__user")
        .order_by("-created_at")
    )
    my_pending = (
        BorrowRequest.objects.filter(faculty=faculty_user, status=BorrowRequest.STATUS_PENDING)
        .select_related("user")
        .order_by("-created_at")
    )
    my_due = (
        BorrowRequest.objects.filter(faculty=faculty_user, status=BorrowRequest.STATUS_APPROVED, due_date=date.today())
        .select_related("user")
        .order_by("due_date")
    )
    return {
        "my_group_requests": my_group_requests,
        "my_pending": my_pending,
        "my_due": my_due,
    }


def get_student_notifications(student_user: User) -> Dict[str, QuerySet]:
    """Retrieve personal borrow request history and status for Student users."""
    my_requests = (
        BorrowRequest.objects.filter(user=student_user)
        .select_related("faculty")
        .order_by("-created_at")
    )
    return {"my_requests": my_requests}


def build_notifications_context(user: User) -> Dict[str, Any]:
    """Build the notification context payload based on user role."""
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)

    context: Dict[str, Any] = {"role": role}

    if role == Profile.ROLE_ADMIN:
        context.update(get_admin_notifications())
    elif role == Profile.ROLE_FACULTY:
        context.update(get_faculty_notifications(user))
    else:
        context.update(get_student_notifications(user))

    return context
