from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Count, Q
from django.utils import timezone

from inventory.models import Component
from requests_app.models import BorrowRequest, BorrowItem, LabPolicy
from users.models import Group, Profile


def _require_role(user, role):
    profile = getattr(user, "profile", None)
    return profile and profile.role == role


def _build_admin_overview_context():
    stats = BorrowRequest.objects.aggregate(
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        issued=Count("id", filter=Q(status=BorrowRequest.STATUS_ISSUED)),
        penalty=Count("id", filter=Q(status=BorrowRequest.STATUS_PENALTY)),
        overdue=Count("id", filter=Q(status=BorrowRequest.STATUS_OVERDUE)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
        rejected=Count("id", filter=Q(status=BorrowRequest.STATUS_REJECTED)),
    )

    pending_groups = Group.objects.filter(status=Group.STATUS_PENDING).count()
    low_stock_count = Component.objects.filter(available_stock__lte=2).count()

    maintenance_keyword_filter = (
        Q(borrow_request__return_condition__icontains="service")
        | Q(borrow_request__return_condition__icontains="damaged")
        | Q(borrow_request__return_condition__icontains="not working")
        | Q(borrow_request__return_condition__icontains="missing")
    )
    maintenance_count = BorrowItem.objects.filter(
        borrow_request__status=BorrowRequest.STATUS_RETURNED,
    ).filter(maintenance_keyword_filter).count()

    priority_items = [
        {
            "label": "Pending Approvals",
            "count": stats.get("pending", 0),
            "href": "admin_requests_console",
            "query": "status=PENDING",
            "severity": "high" if stats.get("pending", 0) > 0 else "ok",
        },
        {
            "label": "Overdue/Penalty",
            "count": (stats.get("overdue", 0) or 0) + (stats.get("penalty", 0) or 0),
            "href": "admin_requests_console",
            "query": "status=OVERDUE",
            "severity": "high" if ((stats.get("overdue", 0) or 0) + (stats.get("penalty", 0) or 0)) > 0 else "ok",
        },
        {
            "label": "Pending Groups",
            "count": pending_groups,
            "href": "admin_groups",
            "query": "",
            "severity": "high" if pending_groups > 0 else "ok",
        },
        {
            "label": "Low Stock",
            "count": low_stock_count,
            "href": "admin_components",
            "query": "stock=low",
            "severity": "warn" if low_stock_count > 0 else "ok",
        },
        {
            "label": "Maintenance Flags",
            "count": maintenance_count,
            "href": "admin_maintenance_console",
            "query": "",
            "severity": "warn" if maintenance_count > 0 else "ok",
        },
    ]
    priority_items = sorted(priority_items, key=lambda row: (row["count"] == 0, -row["count"]))

    urgent_qs = (
        BorrowRequest.objects.filter(status__in=[BorrowRequest.STATUS_PENDING, BorrowRequest.STATUS_OVERDUE, BorrowRequest.STATUS_PENALTY])
        .select_related("user", "faculty", "group")
        .prefetch_related("items__component")
        .order_by("due_date", "-created_at")[:6]
    )
    urgent_ids = [row.id for row in urgent_qs]
    remaining_slots = max(0, 6 - len(urgent_ids))
    latest_qs = (
        BorrowRequest.objects.exclude(id__in=urgent_ids)
        .select_related("user", "faculty", "group")
        .prefetch_related("items__component")
        .order_by("-created_at")[:remaining_slots]
    )
    quick_requests = list(urgent_qs) + list(latest_qs)

    return {
        "stats": stats,
        "quick_requests": quick_requests,
        "low_stock_count": low_stock_count,
        "maintenance_count": maintenance_count,
        "pending_groups_count": pending_groups,
        "priority_items": priority_items,
    }


def _notify_return(borrow_request: BorrowRequest):
    """Send email notifications to faculty and user when a slip is returned."""
    recipients = set()
    if borrow_request.faculty and borrow_request.faculty.email:
        recipients.add(borrow_request.faculty.email)
    if borrow_request.user.email:
        recipients.add(borrow_request.user.email)

    if not recipients:
        return

    subject = f"Borrow slip #{borrow_request.id} returned"
    lines = [
        f"Slip ID: #{borrow_request.id}",
        f"Student: {borrow_request.user.username}",
        f"Faculty: {getattr(borrow_request.faculty, 'username', '—')}",
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


def _component_or_global_fine(component: Component, policy: LabPolicy, component_field: str, policy_field: str) -> int:
    override = getattr(component, component_field, None)
    if override is not None:
        return int(override)
    return int(getattr(policy, policy_field, 0) or 0)


def _calculate_overdue_penalty_estimate(borrow_request: BorrowRequest, policy: LabPolicy):
    due = borrow_request.due_date
    if not due:
        return 0, 0, []
    overdue_days = max(0, (timezone.now().date() - due).days - int(policy.grace_days or 0))
    if overdue_days <= 0:
        return 0, 0, []

    total = 0
    breakdown = []
    for item in borrow_request.items.select_related("component"):
        rate = _component_or_global_fine(item.component, policy, "fine_per_day", "per_day_fine")
        line_total = rate * item.quantity * overdue_days
        total += line_total
        breakdown.append(f"{item.component.name}: {item.quantity} x {overdue_days}d x INR {rate} = INR {line_total}")
    return total, overdue_days, breakdown


def _calculate_condition_penalty_estimate(borrow_request: BorrowRequest, policy: LabPolicy, condition: str):
    normalized = (condition or "").strip().lower()
    if "missing" in normalized:
        component_field = "fine_missing_parts"
        policy_field = "missing_parts_fine"
    elif "not working" in normalized:
        component_field = "fine_not_working"
        policy_field = "not_working_fine"
    elif "damaged" in normalized:
        component_field = "fine_damaged"
        policy_field = "damaged_fine"
    else:
        return 0, []

    total = 0
    breakdown = []
    for item in borrow_request.items.select_related("component"):
        rate = _component_or_global_fine(item.component, policy, component_field, policy_field)
        line_total = rate * item.quantity
        total += line_total
        breakdown.append(f"{item.component.name}: {item.quantity} x INR {rate} = INR {line_total}")
    return total, breakdown
