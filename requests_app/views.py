from collections import defaultdict
from functools import reduce
from operator import or_

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.conf import settings
from django.utils import timezone

from inventory.models import Component
from users.models import Profile
from users.models import Group

from .models import BorrowRequest, BorrowItem, LabPolicy
from .services.borrow_service import (
    BorrowFlowError,
    approve_request,
    mark_request_issued,
    mark_request_penalty,
    mark_request_returned,
    reject_request,
)
from .utils import generate_borrow_slip_pdf


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


# ---------------- Dashboards -----------------
@login_required
def faculty_dashboard(request):
    if not _require_role(request.user, Profile.ROLE_FACULTY):
        messages.error(request, "Only faculty can access this dashboard.")
        return redirect("dashboard")

    status_filter = request.GET.get("status", "").upper()
    search_query = request.GET.get("q", "").strip()
    sort_key = request.GET.get("sort", "created_desc")

    sort_map = {
        "created_desc": "-created_at",
        "created_asc": "created_at",
        "due_asc": "due_date",
        "due_desc": "-due_date",
        "status": "status",
        "student": "user__username",
        "group": "group__code",
    }

    slips_qs = (
        BorrowRequest.objects.filter(faculty=request.user)
        .select_related("user", "faculty", "group")
        .prefetch_related("items__component", "actions")
    )

    if status_filter in dict(BorrowRequest.STATUS_CHOICES):
        slips_qs = slips_qs.filter(status=status_filter)

    if search_query:
        search_filter = Q(user__username__icontains=search_query)
        if search_query.isdigit():
            search_filter |= Q(id=int(search_query))
        slips_qs = slips_qs.filter(search_filter).distinct()

    slips_qs = slips_qs.order_by(sort_map.get(sort_key, "-created_at"))

    try:
        page_size = max(5, min(int(request.GET.get("page_size", 10)), 50))
    except ValueError:
        page_size = 10

    paginator = Paginator(slips_qs, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    stats = slips_qs.aggregate(
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
        rejected=Count("id", filter=Q(status=BorrowRequest.STATUS_REJECTED)),
    )

    base_query = request.GET.copy()
    base_query.pop("page", None)

    context = {
        "page_obj": page_obj,
        "paginator": paginator,
        "status_filter": status_filter,
        "search_query": search_query,
        "sort_key": sort_key,
        "page_size": page_size,
        "stats": stats,
        "total_active": stats.get("pending", 0) + stats.get("approved", 0),
        "awaiting_return": stats.get("approved", 0),
        "querystring_base": base_query.urlencode(),
        "page_sizes": [5, 10, 15, 20, 30, 50],
        "sort_options": sort_map,
    }
    return render(request, "faculty/dashboard.html", context)


@login_required
def _build_admin_queue_context(request):
    status_filter = request.GET.get("status", "").upper()
    search_query = request.GET.get("q", "").strip()
    sort_key = request.GET.get("sort", "created_desc")

    sort_map = {
        "created_desc": "-created_at",
        "created_asc": "created_at",
        "due_asc": "due_date",
        "due_desc": "-due_date",
        "status": "status",
        "student": "user__username",
        "group": "group__code",
    }

    slips_qs = BorrowRequest.objects.all().select_related("user", "faculty", "group").prefetch_related("items__component", "actions")

    if status_filter in dict(BorrowRequest.STATUS_CHOICES):
        slips_qs = slips_qs.filter(status=status_filter)

    if search_query:
        search_filter = (
            Q(user__username__icontains=search_query)
            | Q(faculty__username__icontains=search_query)
            | Q(group__code__icontains=search_query)
            | Q(group__name__icontains=search_query)
        )
        if search_query.isdigit():
            search_filter |= Q(id=int(search_query))
        slips_qs = slips_qs.filter(search_filter).distinct()

    slips_qs = slips_qs.order_by(sort_map.get(sort_key, "-created_at"))

    try:
        page_size = max(5, min(int(request.GET.get("page_size", 10)), 50))
    except ValueError:
        page_size = 10

    paginator = Paginator(slips_qs, page_size)
    page_obj = paginator.get_page(request.GET.get("page"))

    stats = BorrowRequest.objects.aggregate(
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        issued=Count("id", filter=Q(status=BorrowRequest.STATUS_ISSUED)),
        overdue=Count("id", filter=Q(status=BorrowRequest.STATUS_OVERDUE)),
        penalty=Count("id", filter=Q(status=BorrowRequest.STATUS_PENALTY)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
        rejected=Count("id", filter=Q(status=BorrowRequest.STATUS_REJECTED)),
    )

    base_query = request.GET.copy()
    base_query.pop("page", None)

    return {
        "page_obj": page_obj,
        "paginator": paginator,
        "status_filter": status_filter,
        "search_query": search_query,
        "sort_key": sort_key,
        "page_size": page_size,
        "sort_options": sort_map,
        "stats": stats,
        "total_active": stats.get("pending", 0) + stats.get("approved", 0),
        "awaiting_return": stats.get("approved", 0),
        "querystring_base": base_query.urlencode(),
        "page_sizes": [5, 10, 15, 20, 30, 50],
        "queue_total": paginator.count,
    }


@login_required
def admin_dashboard(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access this dashboard.")
        return redirect("dashboard")

    context = _build_admin_overview_context()
    return render(request, "admin/dashboard.html", context)


@login_required
def admin_requests_console(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access request console.")
        return redirect("dashboard")
    return render(request, "admin/request_console.html", _build_admin_queue_context(request))


@login_required
def admin_faculty_console(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access faculty console.")
        return redirect("dashboard")

    low_stock = Component.objects.filter(available_stock__lt=5).order_by("available_stock", "name")[:10]
    recent_components = Component.objects.order_by("-id")[:10]
    faculty_requests = (
        BorrowRequest.objects.filter(user__profile__role=Profile.ROLE_FACULTY)
        .select_related("user", "faculty")
        .prefetch_related("items__component")
        .order_by("-created_at")[:20]
    )

    context = {
        "low_stock": low_stock,
        "recent_components": recent_components,
        "faculty_requests": faculty_requests,
    }
    return render(request, "admin/faculty_console.html", context)


@login_required
def admin_component_console(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access component console.")
        return redirect("dashboard")

    policy, _ = LabPolicy.objects.get_or_create(id=1)
    if request.method == "POST":
        def _safe_int(field_name, current_value):
            raw_value = (request.POST.get(field_name) or "").strip()
            if not raw_value:
                return current_value
            try:
                parsed = int(raw_value)
            except ValueError:
                messages.error(request, f"Invalid number for {field_name.replace('_', ' ')}.")
                return current_value
            return max(0, parsed)

        policy.per_day_fine = _safe_int("per_day_fine", policy.per_day_fine)
        policy.grace_days = _safe_int("grace_days", policy.grace_days)
        policy.overdue_penalty_trigger_days = _safe_int(
            "overdue_penalty_trigger_days", policy.overdue_penalty_trigger_days
        )
        policy.damaged_fine = _safe_int("damaged_fine", policy.damaged_fine)
        policy.missing_parts_fine = _safe_int("missing_parts_fine", policy.missing_parts_fine)
        policy.not_working_fine = _safe_int("not_working_fine", policy.not_working_fine)
        policy.maintenance_keywords = (
            request.POST.get("maintenance_keywords", policy.maintenance_keywords).strip()
        )
        policy.notes = request.POST.get("notes", "").strip()
        policy.save()
        messages.success(request, "Penalty and maintenance policy updated.")
        return redirect("admin_component_console")

    components = Component.objects.all().order_by("name")
    return render(
        request,
        "admin/component_console.html",
        {
            "components": components,
            "policy": policy,
        },
    )


@login_required
def admin_data_console(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access data console.")
        return redirect("dashboard")

    component_query = request.GET.get("component_q", "").strip()
    component_sort = request.GET.get("component_sort", "name")

    stats = BorrowRequest.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        issued=Count("id", filter=Q(status=BorrowRequest.STATUS_ISSUED)),
        penalty=Count("id", filter=Q(status=BorrowRequest.STATUS_PENALTY)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
        overdue=Count("id", filter=Q(status=BorrowRequest.STATUS_OVERDUE)),
        rejected=Count("id", filter=Q(status=BorrowRequest.STATUS_REJECTED)),
    )
    top_components = (
        BorrowItem.objects.values("component__name")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    component_rows = []
    returned_details = []

    collected_statuses = [
        BorrowRequest.STATUS_ISSUED,
        BorrowRequest.STATUS_OVERDUE,
        BorrowRequest.STATUS_PENALTY,
        BorrowRequest.STATUS_RETURNED,
    ]
    damaged_tokens = ("damaged", "not working", "missing", "service")

    components = list(Component.objects.all().order_by("name"))
    component_metrics = {
        c.id: {
            "students_collected": 0,
            "faculty_collected": 0,
            "total_returned": 0,
            "penalized": 0,
            "student_returned": 0,
            "faculty_returned": 0,
            "damaged": 0,
        }
        for c in components
    }

    aggregates = (
        BorrowItem.objects.values(
            "component_id",
            "borrow_request__status",
            "borrow_request__user__profile__role",
        )
        .annotate(total_qty=Sum("quantity"))
    )

    for row in aggregates:
        component_id = row["component_id"]
        status = row["borrow_request__status"]
        role = row["borrow_request__user__profile__role"]
        qty = row["total_qty"] or 0
        metrics = component_metrics.get(component_id)
        if not metrics:
            continue

        if status in collected_statuses:
            if role == Profile.ROLE_STUDENT:
                metrics["students_collected"] += qty
            elif role == Profile.ROLE_FACULTY:
                metrics["faculty_collected"] += qty

        if status == BorrowRequest.STATUS_RETURNED:
            metrics["total_returned"] += qty
            if role == Profile.ROLE_STUDENT:
                metrics["student_returned"] += qty
            elif role == Profile.ROLE_FACULTY:
                metrics["faculty_returned"] += qty

        if status == BorrowRequest.STATUS_PENALTY:
            metrics["penalized"] += qty

    condition_query = reduce(
        or_,
        [Q(borrow_request__return_condition__icontains=token) for token in damaged_tokens],
    )
    damaged_by_component = defaultdict(int)
    damaged_items_qs = (
        BorrowItem.objects.filter(borrow_request__status=BorrowRequest.STATUS_RETURNED)
        .filter(condition_query)
        .select_related("component", "borrow_request__user__profile")
        .order_by("-borrow_request__return_time")
    )
    for row in damaged_items_qs.values("component_id").annotate(total_qty=Sum("quantity")):
        damaged_by_component[row["component_id"]] = row["total_qty"] or 0
    for component_id, qty in damaged_by_component.items():
        metrics = component_metrics.get(component_id)
        if metrics:
            metrics["damaged"] = qty

    returned_details = [
        {
            "component": item.component.name,
            "returner": item.borrow_request.user.username,
            "role": getattr(getattr(item.borrow_request.user, "profile", None), "role", "") or "unknown",
            "condition": item.borrow_request.return_condition or "Not specified",
            "returned_at": item.borrow_request.return_time,
            "quantity": item.quantity,
        }
        for item in damaged_items_qs[:20]
    ]

    for component in components:
        metrics = component_metrics[component.id]
        students_collected = metrics["students_collected"]
        faculty_collected = metrics["faculty_collected"]
        total_returned = metrics["total_returned"]
        penalized = metrics["penalized"]
        damaged = metrics["damaged"]
        student_returned = metrics["student_returned"]
        faculty_returned = metrics["faculty_returned"]

        total_collected = students_collected + faculty_collected
        utilization_pct = round((total_collected / component.total_stock) * 100, 1) if component.total_stock else 0
        return_rate_pct = round((total_returned / total_collected) * 100, 1) if total_collected else 0
        penalty_rate_pct = round((penalized / total_collected) * 100, 1) if total_collected else 0
        risk_score = penalized + damaged + (3 if component.available_stock <= 2 else 0)
        component_rows.append(
            {
                "name": component.name,
                "total_stock": component.total_stock,
                "available_stock": component.available_stock,
                "students_collected": students_collected,
                "faculty_collected": faculty_collected,
                "total_collected": total_collected,
                "total_returned": total_returned,
                "penalized": penalized,
                "student_returned": student_returned,
                "faculty_returned": faculty_returned,
                "damaged": damaged,
                "utilization_pct": utilization_pct,
                "return_rate_pct": return_rate_pct,
                "penalty_rate_pct": penalty_rate_pct,
                "risk_score": risk_score,
            }
        )

    if component_query:
        component_rows = [
            row for row in component_rows if component_query.lower() in row["name"].lower()
        ]

    sort_map = {
        "name": lambda x: x["name"].lower(),
        "utilization": lambda x: x["utilization_pct"],
        "penalty": lambda x: x["penalized"],
        "damage": lambda x: x["damaged"],
        "available": lambda x: x["available_stock"],
        "risk": lambda x: x["risk_score"],
    }
    reverse_sort = component_sort in {"utilization", "penalty", "damage", "risk"}
    component_rows = sorted(
        component_rows,
        key=sort_map.get(component_sort, sort_map["name"]),
        reverse=reverse_sort,
    )

    chart_source = component_rows[:12]
    chart_labels = [row["name"] for row in chart_source]
    chart_collected = [row["total_collected"] for row in chart_source]
    chart_returned = [row["total_returned"] for row in chart_source]
    chart_penalized = [row["penalized"] for row in chart_source]

    status_labels = ["Pending", "Approved", "Issued", "Returned", "Penalty", "Overdue", "Rejected"]
    status_values = [
        stats.get("pending", 0),
        stats.get("approved", 0),
        stats.get("issued", 0),
        stats.get("returned", 0),
        stats.get("penalty", 0),
        stats.get("overdue", 0),
        stats.get("rejected", 0),
    ]

    total_requests = stats.get("total", 0) or 0
    completed_requests = stats.get("returned", 0) + stats.get("rejected", 0)
    active_requests = total_requests - completed_requests
    penalty_rate = round((stats.get("penalty", 0) / total_requests) * 100, 1) if total_requests else 0
    return_rate = round((stats.get("returned", 0) / total_requests) * 100, 1) if total_requests else 0

    total_stock = sum(row["total_stock"] for row in component_rows) or 0
    total_available = sum(row["available_stock"] for row in component_rows)
    utilization_rate = round(((total_stock - total_available) / total_stock) * 100, 1) if total_stock else 0

    high_risk_components = [row for row in component_rows if row["risk_score"] >= 3][:8]
    risky_returns_count = damaged_items_qs.count()

    insights = []
    high_penalty = [row for row in component_rows if row["penalized"] >= 3]
    low_availability = [row for row in component_rows if row["available_stock"] <= 2]
    damage_prone = [row for row in component_rows if row["damaged"] >= 2]
    if high_penalty:
        names = ", ".join(row["name"] for row in high_penalty[:3])
        insights.append(f"Penalty risk is concentrated in: {names}. Consider shorter checkout window or stricter approval.")
    if low_availability:
        names = ", ".join(row["name"] for row in low_availability[:3])
        insights.append(f"Low available stock alert: {names}. Reorder or reduce per-user limits temporarily.")
    if damage_prone:
        names = ", ".join(row["name"] for row in damage_prone[:3])
        insights.append(f"Frequent damage flagged for: {names}. Add mandatory condition checklist at issue/return.")
    if not insights:
        insights.append("No abnormal trend detected. Stock, returns, and penalties look stable this cycle.")

    return render(
        request,
        "admin/data_console.html",
        {
            "stats": stats,
            "active_requests": active_requests,
            "completed_requests": completed_requests,
            "penalty_rate": penalty_rate,
            "return_rate": return_rate,
            "utilization_rate": utilization_rate,
            "risky_returns_count": risky_returns_count,
            "top_components": top_components,
            "component_rows": component_rows,
            "high_risk_components": high_risk_components,
            "returned_details": returned_details[:20],
            "chart_labels": chart_labels,
            "chart_collected": chart_collected,
            "chart_returned": chart_returned,
            "chart_penalized": chart_penalized,
            "status_labels": status_labels,
            "status_values": status_values,
            "ai_insights": insights,
            "component_query": component_query,
            "component_sort": component_sort,
        },
    )


@login_required
def admin_maintenance_queue(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access maintenance queue.")
        return redirect("dashboard")

    policy, _ = LabPolicy.objects.get_or_create(id=1)
    keywords = [
        kw.strip().lower()
        for kw in (policy.maintenance_keywords or "").split(",")
        if kw.strip()
    ]

    returned_items = (
        BorrowItem.objects.filter(borrow_request__status=BorrowRequest.STATUS_RETURNED)
        .select_related("component", "borrow_request__user")
        .order_by("-borrow_request__return_time")
    )
    if keywords:
        keyword_query = reduce(
            or_,
            [Q(borrow_request__return_condition__icontains=kw) for kw in keywords],
        )
        maintenance_items = list(returned_items.filter(keyword_query)[:50])
    else:
        maintenance_items = []

    low_stock = Component.objects.filter(available_stock__lte=2).order_by("available_stock", "name")
    penalty_reqs = (
        BorrowRequest.objects.filter(status=BorrowRequest.STATUS_PENALTY)
        .select_related("user", "faculty")
        .order_by("-created_at")
    )
    return render(
        request,
        "admin/maintenance_queue.html",
        {
            "policy": policy,
            "maintenance_items": maintenance_items,
            "low_stock": low_stock,
            "penalty_reqs": penalty_reqs,
        },
    )


@login_required
def admin_reports_console(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access reports console.")
        return redirect("dashboard")

    totals = BorrowRequest.objects.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status__in=[BorrowRequest.STATUS_PENDING, BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_ISSUED])),
        overdue=Count("id", filter=Q(status=BorrowRequest.STATUS_OVERDUE)),
        penalty=Count("id", filter=Q(status=BorrowRequest.STATUS_PENALTY)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
    )
    role_split = BorrowRequest.objects.values("user__profile__role").annotate(total=Count("id")).order_by("user__profile__role")
    top_users = (
        BorrowItem.objects.values("borrow_request__user__username")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")[:10]
    )
    return render(
        request,
        "admin/reports_console.html",
        {
            "totals": totals,
            "role_split": role_split,
            "top_users": top_users,
        },
    )


# ----------------- Actions --------------------
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

    # permission: student owner, faculty assigned, or admin
    profile = getattr(request.user, "profile", None)
    role = getattr(profile, "role", None)
    same_student_group = (
        role == Profile.ROLE_STUDENT
        and slip.group_id is not None
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
    from django.http import HttpResponse

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename=\"{filename}\"'
    return response
