from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect

from requests_app.models import BorrowRequest, LabPolicy
from requests_app.services.borrow_service import (
    BorrowFlowError,
    approve_request,
    mark_request_issued,
    mark_request_penalty,
    mark_request_returned,
    reject_request,
)
from requests_app.utils import generate_borrow_slip_pdf
from users.models import Profile

from .common import (
    _require_role,
    _notify_return,
    _calculate_overdue_penalty_estimate,
    _calculate_condition_penalty_estimate,
)


@login_required
def terminate_slip(request, request_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_dashboard")
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role not in (Profile.ROLE_ADMIN, Profile.ROLE_FACULTY):
        messages.error(request, "You are not authorized to reject slips.")
        return redirect("dashboard")
    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    if role == Profile.ROLE_FACULTY and borrow_request.faculty != request.user:
        messages.error(request, "You can reject only requests assigned to you.")
        return redirect("faculty_dashboard")
    note = request.POST.get("reject_note", "").strip()
    if not note:
        note = "Rejected without remarks"

    try:
        reject_request(borrow_request, by_user=request.user, note=note)
    except BorrowFlowError as exc:
        messages.info(request, str(exc))
        return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_requests_console")
    messages.warning(request, "Borrow request rejected and stock restored.")
    return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_requests_console")


@login_required
def mark_returned(request, request_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_requests_console")
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can mark returns.")
        return redirect("dashboard")

    condition = request.POST.get("condition", "").strip()
    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    policy, _ = LabPolicy.objects.get_or_create(id=1)
    try:
        mark_request_returned(borrow_request, by_user=request.user, condition=condition)
    except BorrowFlowError as exc:
        messages.info(request, str(exc))
        return redirect("admin_requests_console")
    condition_total, _ = _calculate_condition_penalty_estimate(borrow_request, policy, condition)
    if condition_total > 0:
        messages.warning(
            request,
            f"Items marked as returned. Estimated condition fine (component-wise): INR {condition_total}.",
        )
    else:
        messages.success(request, "Items marked as returned and stock restored.")
    _notify_return(borrow_request)
    return redirect("admin_requests_console")


@login_required
def mark_issued(request, request_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_requests_console")
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can mark collection.")
        return redirect("dashboard")

    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    collector_name = request.POST.get("collector_name", "").strip()
    if not collector_name:
        messages.error(request, "Collector name is required before marking as collected.")
        return redirect("admin_requests_console")
    try:
        mark_request_issued(
            borrow_request,
            by_user=request.user,
            note=f"Collected by {collector_name}",
        )
    except BorrowFlowError as exc:
        messages.info(request, str(exc))
        return redirect("admin_requests_console")
    messages.success(request, "Collection recorded.")
    return redirect("admin_requests_console")


@login_required
def mark_penalty(request, request_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_requests_console")
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can apply penalty status.")
        return redirect("dashboard")

    borrow_request = get_object_or_404(BorrowRequest, id=request_id)
    manual_note = request.POST.get("note", "").strip()
    policy, _ = LabPolicy.objects.get_or_create(id=1)
    estimated_total, overdue_days, breakdown = _calculate_overdue_penalty_estimate(borrow_request, policy)
    auto_note = ""
    if overdue_days > 0:
        auto_note = (
            f"Estimated overdue fine: INR {estimated_total} (overdue days after grace: {overdue_days}). "
            f"Breakdown: {' | '.join(breakdown)}"
        )
    note = auto_note
    if manual_note:
        note = f"{auto_note} | Admin note: {manual_note}" if auto_note else manual_note
    try:
        mark_request_penalty(borrow_request, by_user=request.user, note=note)
    except BorrowFlowError as exc:
        messages.info(request, str(exc))
        return redirect("admin_requests_console")
    if overdue_days > 0:
        messages.warning(
            request,
            f"Penalty stage recorded. Estimated overdue fine (component-wise): INR {estimated_total}.",
        )
    else:
        messages.warning(request, "Penalty stage recorded. No overdue charge estimated yet.")
    return redirect("admin_requests_console")


@login_required
def approve_slip(request, request_id):
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect("admin_requests_console")
    role = getattr(getattr(request.user, "profile", None), "role", None)
    slip = get_object_or_404(BorrowRequest, id=request_id)
    if role == Profile.ROLE_FACULTY and slip.faculty != request.user:
        messages.error(request, "You are not assigned to this request.")
        return redirect("dashboard")
    if role not in (Profile.ROLE_FACULTY, Profile.ROLE_ADMIN):
        messages.error(request, "You are not authorized to approve requests.")
        return redirect("dashboard")

    if slip.status != BorrowRequest.STATUS_PENDING:
        messages.info(request, "Request already processed.")
        return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_requests_console")

    try:
        approve_request(slip, by_user=request.user)
    except BorrowFlowError as exc:
        messages.info(request, str(exc))
        return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_requests_console")

    messages.success(request, "Request approved.")
    return redirect("faculty_dashboard" if role == Profile.ROLE_FACULTY else "admin_requests_console")


@login_required
def download_slip(request, request_id):
    slip = get_object_or_404(BorrowRequest, id=request_id)

    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)
    same_student_group = (
        role == Profile.ROLE_STUDENT
        and slip.group_id is not None
        and slip.group is not None
        and profile is not None
        and (profile.group_id or "").upper() == (slip.group.code or "").upper()
    )

    if not (
        slip.user == request.user
        or slip.faculty == request.user
        or same_student_group
        or role == Profile.ROLE_ADMIN
    ):
        messages.error(request, "You do not have permission to download this slip.")
        return redirect("dashboard")

    filename, pdf_bytes = generate_borrow_slip_pdf(slip.id)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
