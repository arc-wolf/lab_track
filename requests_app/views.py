from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from inventory.models import Component
from users.models import Profile

from .models import BorrowRequest
from .utils import build_request_pdf


def _require_role(user, role):
    profile = getattr(user, "profile", None)
    return profile and profile.role == role


@login_required
def faculty_dashboard(request):
    if not _require_role(request.user, Profile.ROLE_FACULTY):
        return redirect("dashboard")

    slips = (
        BorrowRequest.objects.filter(faculty=request.user)
        .select_related("student")
        .prefetch_related("items__component")
        .order_by("-created_at")
    )
    return render(request, "faculty/dashboard.html", {"slips": slips})


@login_required
def admin_dashboard(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    slips = (
        BorrowRequest.objects.all()
        .select_related("student")
        .prefetch_related("items__component")
        .order_by("-created_at")
    )
    return render(request, "admin/dashboard.html", {"slips": slips})


@login_required
def terminate_slip(request, request_id):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    if borrow_request.status not in (BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_PENDING):
        messages.info(request, "Request already closed.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        for item in borrow_request.items.select_related("component"):
            component = Component.objects.select_for_update().get(id=item.component_id)
            component.available_stock = component.available_stock + item.quantity
            component.save()
        borrow_request.status = BorrowRequest.STATUS_TERMINATED
        borrow_request.save()
    messages.warning(request, "Borrow request terminated and stock restored.")
    return redirect("admin_dashboard")


@login_required
def mark_returned(request, request_id):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    if borrow_request.status != BorrowRequest.STATUS_APPROVED:
        messages.info(request, "Request already closed.")
        return redirect("admin_dashboard")

    with transaction.atomic():
        for item in borrow_request.items.select_related("component"):
            component = Component.objects.select_for_update().get(id=item.component_id)
            component.available_stock = component.available_stock + item.quantity
            component.save()
        borrow_request.status = BorrowRequest.STATUS_RETURNED
        borrow_request.save()
    messages.success(request, "Items marked as returned and stock restored.")
    return redirect("admin_dashboard")


@login_required
def approve_slip(request, request_id):
    # Faculty can approve their assigned; admin can approve any pending
    slip = get_object_or_404(BorrowRequest, id=request_id)
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role == Profile.ROLE_FACULTY and slip.faculty != request.user:
        return redirect("dashboard")
    if role not in (Profile.ROLE_FACULTY, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    if slip.status != BorrowRequest.STATUS_PENDING:
        messages.info(request, "Request already processed.")
        return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_dashboard")

    slip.status = BorrowRequest.STATUS_APPROVED
    slip.save()
    messages.success(request, "Request approved.")
    return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_dashboard")


@login_required
def download_slip(request, request_id):
    slip = get_object_or_404(BorrowRequest, id=request_id)

    # permission: student owner, faculty assigned, or admin
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if not (
        slip.student == request.user
        or slip.faculty == request.user
        or role == Profile.ROLE_ADMIN
    ):
        return redirect("dashboard")

    filename, pdf_bytes = build_request_pdf(slip)
    from django.http import HttpResponse

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
