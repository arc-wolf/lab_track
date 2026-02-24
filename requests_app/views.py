from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings

from inventory.models import Component
from users.models import Profile

from .models import BorrowRequest
from .utils import build_request_pdf


def _require_role(user, role):
    profile = getattr(user, "profile", None)
    return profile and profile.role == role


def _notify_return(borrow_request: BorrowRequest):
    """
    Send email notifications to faculty in-charge and group members when a slip is returned.
    Uses fail_silently to avoid blocking the flow if SMTP is misconfigured.
    """
    recipients = set()
    group = borrow_request.group
    if group and group.faculty and group.faculty.email:
        recipients.add(group.faculty.email)
    if group:
        for member in group.members.select_related("user"):
            if member.user.email:
                recipients.add(member.user.email)

    if not recipients:
        return

    subject = f"Borrow slip #{borrow_request.id} returned"
    lines = [
        f"Slip ID: #{borrow_request.id}",
        f"Student: {borrow_request.student.username}",
        f"Faculty: {getattr(group.faculty, 'username', '—') if group else '—'}",
        f"Return time: {borrow_request.return_time}",
        f"Condition: {borrow_request.return_condition or 'Not specified'}",
        "Items:",
    ]
    for item in borrow_request.items.select_related("component"):
        lines.append(f"- {item.component.name} x {item.quantity}")
    message = "\n".join(lines)
    send_mail(
        subject,
        message,
        getattr(settings, "DEFAULT_FROM_EMAIL", "labtrack@localhost"),
        list(recipients),
        fail_silently=True,
    )


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
    if request.method != "POST":
        return redirect("admin_dashboard")
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
    messages.warning(request, "Borrow request rejected and stock restored.")
    return redirect("admin_dashboard")


@login_required
def mark_returned(request, request_id):
    if request.method != "POST":
        return redirect("admin_dashboard")
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    condition = request.POST.get("condition", "").strip()
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
        borrow_request.return_condition = condition
        borrow_request.return_time = timezone.now()
        borrow_request.save(update_fields=["status", "return_condition", "return_time"])
    messages.success(request, "Items marked as returned and stock restored.")
    _notify_return(borrow_request)
    return redirect("admin_dashboard")


@login_required
def approve_slip(request, request_id):
    if request.method != "POST":
        return redirect("admin_dashboard")
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
    slip.save(update_fields=["status"])
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
