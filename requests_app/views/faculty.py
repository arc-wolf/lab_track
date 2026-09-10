from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from requests_app.models import BorrowRequest
from users.models import Profile
from .common import _require_role


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
