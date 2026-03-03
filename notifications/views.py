from datetime import date

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect

from inventory.models import Component
from requests_app.models import BorrowRequest
from users.models import Group, Profile


@login_required
def notifications_center(request):
    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)

    context = {"role": role}

    if role == Profile.ROLE_ADMIN:
        low_stock = Component.objects.filter(available_stock__lte=2).order_by("available_stock", "name")
        pending = BorrowRequest.objects.filter(status=BorrowRequest.STATUS_PENDING).order_by("-created_at")
        due_today = BorrowRequest.objects.filter(
            status=BorrowRequest.STATUS_APPROVED, due_date=date.today()
        ).select_related("user", "faculty")
        context.update(
            {
                "low_stock": low_stock,
                "pending": pending,
                "due_today": due_today,
            }
        )
    elif role == Profile.ROLE_FACULTY:
        Group.objects.filter(
            faculty__isnull=True
        ).filter(
            Q(members__user__profile__faculty_incharge=request.user.username)
            | Q(members__user__profile__faculty_incharge=request.user.email)
            | Q(members__user__profile__faculty_incharge=request.user.profile.full_name)
        ).update(faculty=request.user)

        my_group_requests = (
            Group.objects.filter(faculty=request.user, status=Group.STATUS_PENDING)
            .prefetch_related("members__user")
            .order_by("-created_at")
        )
        my_pending = (
            BorrowRequest.objects.filter(faculty=request.user, status=BorrowRequest.STATUS_PENDING)
            .select_related("user")
            .order_by("-created_at")
        )
        my_due = (
            BorrowRequest.objects.filter(faculty=request.user, status=BorrowRequest.STATUS_APPROVED, due_date=date.today())
            .select_related("user")
            .order_by("due_date")
        )
        context.update(
            {
                "my_group_requests": my_group_requests,
                "my_pending": my_pending,
                "my_due": my_due,
            }
        )
    else:
        # students or others
        my_requests = (
            BorrowRequest.objects.filter(user=request.user)
            .select_related("faculty")
            .order_by("-created_at")
        )
        context.update({"my_requests": my_requests})

    return render(request, "notifications/center.html", context)
