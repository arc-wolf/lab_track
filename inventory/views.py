from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from requests_app.models import BorrowRequest
from requests_app.services import get_requests_for_user
from users.models import Group, GroupMember, Profile
from .forms import ComponentForm
from .models import Component, Reservation
from .services.cart_service import (
    CartAccessError,
    assert_group_cart_access,
    create_borrow_request_from_cart,
    sync_group_cart_lock,
)
from .services import excel_service


# --------- helpers ---------------------------------------------------------
def _require_role(user, role):
    profile = getattr(user, "profile", None)
    return profile and profile.role == role


def _is_borrower(user):
    profile = getattr(user, "profile", None)
    return profile and profile.role in (Profile.ROLE_STUDENT, Profile.ROLE_FACULTY)


def _ensure_group(user):
    """
    Ensure group/membership exists for students and report approval status.
    """
    profile = getattr(user, "profile", None)
    if not profile or profile.role != Profile.ROLE_STUDENT:
        return None, True
    if not profile.group_id:
        return None, False

    group, _ = Group.objects.get_or_create(
        code=profile.group_id,
        defaults={"name": profile.group_name or ""},
    )
    if profile.group_name and group.name != profile.group_name:
        group.name = profile.group_name
        group.save(update_fields=["name"])
    if profile.faculty_incharge and not group.faculty:
        faculty = (
            Profile.objects.filter(role=Profile.ROLE_FACULTY)
            .filter(
                Q(user__username=profile.faculty_incharge)
                | Q(user__email__iexact=profile.faculty_incharge)
                | Q(full_name__iexact=profile.faculty_incharge)
            )
            .select_related("user")
            .first()
        )
        if faculty:
            group.faculty = faculty.user
            group.save(update_fields=["faculty"])

    GroupMember.objects.get_or_create(
        group=group, user=user, defaults={"role": GroupMember.ROLE_MEMBER}
    )
    return group, group.status == Group.STATUS_APPROVED


def _group_member_ids(group):
    if not group:
        return []
    return list(group.members.values_list("user_id", flat=True))


def _clean_expired_reservations(user=None, user_ids=None):
    qs = Reservation.objects.filter(is_active=True, expires_at__lte=timezone.now())
    if user_ids is not None:
        qs = qs.filter(user_id__in=user_ids)
    elif user:
        qs = qs.filter(user=user)
    for res in qs.select_related("component"):
        res.expire_and_release()


# ---------------- Student flows -------------------------------------------
@login_required
def student_dashboard(request):
    if not _is_borrower(request.user):
        messages.error(request, "You do not have access to the component console.")
        return redirect("dashboard")

    group, is_group_approved = _ensure_group(request.user)
    member_ids = _group_member_ids(group) if request.user.profile.role == Profile.ROLE_STUDENT else []
    _clean_expired_reservations(request.user, user_ids=member_ids if member_ids else None)

    category_filter = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    components = Component.objects.all().order_by("-available_stock", "name")
    if category_filter:
        components = components.filter(category=category_filter)
    if search_query:
        components = components.filter(name__icontains=search_query)

    categories = cache.get("inventory_categories_v1")
    if categories is None:
        categories = list(Component.objects.values_list("category", flat=True).distinct())
        cache.set("inventory_categories_v1", categories, timeout=300)

    # summary
    if request.user.profile.role == Profile.ROLE_STUDENT and group:
        pending_requests = BorrowRequest.objects.filter(group=group, status=BorrowRequest.STATUS_PENDING).count()
        active_borrows = BorrowRequest.objects.filter(
            group=group, status__in=[BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_ISSUED, BorrowRequest.STATUS_OVERDUE]
        ).count()
        current_reserved = (
            Reservation.objects.filter(user_id__in=member_ids, is_active=True).aggregate(total=Sum("quantity")).get("total") or 0
        )
    else:
        pending_requests = BorrowRequest.objects.filter(user=request.user, status=BorrowRequest.STATUS_PENDING).count()
        active_borrows = BorrowRequest.objects.filter(
            user=request.user, status__in=[BorrowRequest.STATUS_APPROVED, BorrowRequest.STATUS_ISSUED, BorrowRequest.STATUS_OVERDUE]
        ).count()
        current_reserved = (
            Reservation.objects.filter(user=request.user, is_active=True).aggregate(total=Sum("quantity")).get("total") or 0
        )
    max_allowed = getattr(settings, "STUDENT_MAX_ACTIVE", 10)
    quota_remaining = max(max_allowed - current_reserved, 0)

    return render(
        request,
        "student/dashboard.html",
        {
            "components": components,
            "categories": categories,
            "selected_category": category_filter,
            "group_status": group.status if group else None,
            "group": group,
            "can_borrow": bool(is_group_approved),
            "summary": {
                "pending": pending_requests,
                "active": active_borrows,
                "max_allowed": max_allowed,
                "reserved": current_reserved,
                "remaining": quota_remaining,
            },
            "search_query": search_query,
            "shared_mode": bool(request.user.profile.role == Profile.ROLE_STUDENT and group),
            "group_member_count": len(member_ids) if member_ids else 1,
            "quota_remaining": quota_remaining,
        },
    )


@login_required
def add_to_cart(request, component_id):
    if request.method != "POST" or not _is_borrower(request.user):
        return redirect("student_dashboard")

    group, is_group_approved = _ensure_group(request.user)
    member_ids = _group_member_ids(group) if request.user.profile.role == Profile.ROLE_STUDENT else []
    _clean_expired_reservations(request.user, user_ids=member_ids if member_ids else None)
    if request.user.profile.role == Profile.ROLE_STUDENT and not is_group_approved:
        messages.error(request, "Group pending faculty approval. Borrowing is locked until approval.")
        return redirect("student_dashboard")

    try:
        quantity = int(request.POST.get("quantity", 0))
    except ValueError:
        quantity = 0
    component = get_object_or_404(Component, id=component_id)

    max_allowed = getattr(settings, "STUDENT_MAX_ACTIVE", 10)
    if max_allowed:
        if request.user.profile.role == Profile.ROLE_STUDENT and member_ids:
            reserved_total = (
                Reservation.objects.filter(user_id__in=member_ids, is_active=True)
                .aggregate(total=Sum("quantity"))
                .get("total")
                or 0
            )
        else:
            reserved_total = (
                Reservation.objects.filter(user=request.user, is_active=True)
                .aggregate(total=Sum("quantity"))
                .get("total")
                or 0
            )
        if reserved_total + quantity > max_allowed:
            messages.error(
                request,
                f"Limit reached: Max {max_allowed} active reservations. Current reserved {reserved_total}.",
            )
            return redirect("student_dashboard")

    if quantity <= 0:
        messages.error(request, "Quantity must be greater than zero.")
        return redirect("student_dashboard")

    with transaction.atomic():
        locked = Component.objects.select_for_update().get(id=component.id)
        if request.user.profile.role == Profile.ROLE_STUDENT and group:
            try:
                assert_group_cart_access(group, request.user)
            except CartAccessError as exc:
                messages.error(request, str(exc))
                return redirect("student_dashboard")
        limit = locked.student_limit if request.user.profile.role == Profile.ROLE_STUDENT else locked.faculty_limit
        if locked.available_stock < quantity:
            messages.error(request, "Requested quantity exceeds available stock.")
            return redirect("student_dashboard")

        if request.user.profile.role == Profile.ROLE_STUDENT and member_ids:
            existing_qs = Reservation.objects.select_for_update().filter(
                user_id__in=member_ids, component=locked, is_active=True
            )
        else:
            existing_qs = Reservation.objects.select_for_update().filter(
                user=request.user, component=locked, is_active=True
            )

        existing = existing_qs.first()
        if existing:
            new_qty = existing.quantity + quantity
            if limit and new_qty > limit:
                messages.error(request, f"Limit per user: {limit}.")
                return redirect("student_dashboard")
            locked.adjust_available(-quantity)
            existing.quantity = new_qty
            existing.expires_at = timezone.now() + timedelta(minutes=15)
            existing.save(update_fields=["quantity", "expires_at"])
            if request.user.profile.role == Profile.ROLE_STUDENT and group:
                all_reservations = list(
                    Reservation.objects.filter(user_id__in=member_ids, is_active=True)
                )
                sync_group_cart_lock(group, request.user, all_reservations)
            messages.success(request, f"Updated team cart for {component.name} (now {new_qty}).")
            return redirect("student_dashboard")

        if limit and quantity > limit:
            messages.error(request, f"Limit per user: {limit}.")
            return redirect("student_dashboard")
        locked.adjust_available(-quantity)
        Reservation.objects.create(
            user=request.user,
            component=locked,
            quantity=quantity,
            expires_at=timezone.now() + timedelta(minutes=15),
            is_active=True,
        )
        if request.user.profile.role == Profile.ROLE_STUDENT and group:
            all_reservations = list(
                Reservation.objects.filter(user_id__in=member_ids, is_active=True)
            )
            sync_group_cart_lock(group, request.user, all_reservations)

    messages.success(request, f"Reserved {quantity} x {component.name} for 15 minutes.")
    return redirect("student_dashboard")


@login_required
def view_cart(request):
    if not _is_borrower(request.user):
        messages.error(request, "You do not have access to the cart.")
        return redirect("dashboard")

    group, is_group_approved = _ensure_group(request.user)
    member_ids = _group_member_ids(group) if request.user.profile.role == Profile.ROLE_STUDENT else []
    _clean_expired_reservations(request.user, user_ids=member_ids if member_ids else None)
    if request.user.profile.role == Profile.ROLE_STUDENT and not is_group_approved:
        messages.error(request, "Group pending faculty approval. Borrowing is locked until approval.")
        return redirect("student_dashboard")
    if request.user.profile.role == Profile.ROLE_STUDENT and group:
        try:
            with transaction.atomic():
                group_reservations = list(
                    Reservation.objects.filter(user_id__in=member_ids, is_active=True)
                )
                sync_group_cart_lock(group, request.user, group_reservations)
        except CartAccessError as exc:
            messages.error(request, str(exc))
            return redirect("student_dashboard")

    if request.user.profile.role == Profile.ROLE_STUDENT and member_ids:
        reservations = (
            Reservation.objects.filter(user_id__in=member_ids, is_active=True)
            .select_related("component", "user")
            .order_by("-reserved_at")
        )
    else:
        reservations = (
            Reservation.objects.filter(user=request.user, is_active=True)
            .select_related("component", "user")
            .order_by("-reserved_at")
        )
    faculties = Profile.objects.filter(role=Profile.ROLE_FACULTY).select_related("user")
    return render(
        request,
        "student/cart.html",
        {
            "reservations": reservations,
            "faculties": faculties,
            "group": group,
            "shared_mode": bool(request.user.profile.role == Profile.ROLE_STUDENT and group),
            "is_faculty_user": request.user.profile.role == Profile.ROLE_FACULTY,
            "preassigned_faculty": getattr(group, "faculty", None) if group else None,
        },
    )


@login_required
def remove_cart_item(request, reservation_id):
    if not _is_borrower(request.user):
        messages.error(request, "You do not have permission to edit this cart.")
        return redirect("dashboard")
    if request.method != "POST":
        messages.error(request, "Invalid action. Please remove items using the cart buttons.")
        return redirect("view_cart")

    group, _ = _ensure_group(request.user)
    member_ids = _group_member_ids(group) if request.user.profile.role == Profile.ROLE_STUDENT else []
    if request.user.profile.role == Profile.ROLE_STUDENT and member_ids:
        res = get_object_or_404(
            Reservation,
            id=reservation_id,
            user_id__in=member_ids,
            is_active=True,
        )
    else:
        res = get_object_or_404(Reservation, id=reservation_id, user=request.user, is_active=True)
    with transaction.atomic():
        if request.user.profile.role == Profile.ROLE_STUDENT and group:
            member_reservations = list(
                Reservation.objects.filter(user_id__in=member_ids, is_active=True)
            )
            try:
                sync_group_cart_lock(group, request.user, member_reservations)
            except CartAccessError as exc:
                messages.error(request, str(exc))
                return redirect("view_cart")
        res.expire_and_release()
        if request.user.profile.role == Profile.ROLE_STUDENT and group:
            remaining = list(
                Reservation.objects.filter(user_id__in=member_ids, is_active=True)
            )
            sync_group_cart_lock(group, request.user, remaining)
    messages.info(request, "Reservation removed and stock restored.")
    return redirect("view_cart")


@login_required
def generate_slip(request):
    if request.method != "POST" or not _is_borrower(request.user):
        messages.error(request, "Invalid request. Generate the slip from the cart page.")
        return redirect("view_cart")

    group, is_group_approved = _ensure_group(request.user)
    member_ids = _group_member_ids(group) if request.user.profile.role == Profile.ROLE_STUDENT else []
    _clean_expired_reservations(request.user, user_ids=member_ids if member_ids else None)
    if request.user.profile.role == Profile.ROLE_STUDENT and not is_group_approved:
        messages.error(request, "Group pending faculty approval. Borrowing is locked until approval.")
        return redirect("student_dashboard")
    if request.user.profile.role == Profile.ROLE_STUDENT and member_ids:
        reservations_qs = Reservation.objects.filter(user_id__in=member_ids, is_active=True)
    else:
        reservations_qs = Reservation.objects.filter(user=request.user, is_active=True)
    reservations = list(
        reservations_qs.select_related("component", "user").order_by("reserved_at")
    )
    if not reservations:
        messages.error(request, "Your cart is empty or reservations expired.")
        return redirect("view_cart")

    project_title = request.POST.get("project_title", "").strip()
    if not project_title:
        messages.error(request, "Project title is required.")
        return redirect("view_cart")
    try:
        create_borrow_request_from_cart(
            actor=request.user,
            group=group,
            project_title=project_title,
        )
    except CartAccessError as exc:
        messages.error(request, str(exc))
        return redirect("view_cart")

    messages.success(request, "Borrow slip generated. Awaiting approval.")
    return redirect("student_requests")


@login_required
def student_requests(request):
    if not _is_borrower(request.user):
        messages.error(request, "You do not have access to request history.")
        return redirect("dashboard")

    group, _ = _ensure_group(request.user)
    slips = (
        get_requests_for_user(request.user, BorrowRequest.objects.all())
        .select_related("user", "faculty")
        .prefetch_related("items__component")
        .order_by("-created_at")
    )
    return render(
        request,
        "student/requests.html",
        {"slips": slips, "shared_mode": bool(request.user.profile.role == Profile.ROLE_STUDENT and group)},
    )


# ---------------- Admin inventory management ----------------
@login_required
def admin_components(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can access stock console.")
        return redirect("dashboard")

    category_filter = request.GET.get("category", "")
    search_query = request.GET.get("q", "").strip()
    stock_filter = request.GET.get("stock", "")
    components = Component.objects.all().order_by("name")
    if category_filter:
        components = components.filter(category=category_filter)
    if search_query:
        components = components.filter(name__icontains=search_query)
    if stock_filter == "low":
        components = components.filter(available_stock__gt=0, available_stock__lte=2)
    elif stock_filter == "out":
        components = components.filter(available_stock=0)
    categories = Component.objects.values_list("category", flat=True).distinct()
    return render(
        request,
        "admin/components.html",
        {
            "components": components,
            "categories": categories,
            "selected_category": category_filter,
            "search_query": search_query,
            "stock_filter": stock_filter,
        },
    )


@login_required
def admin_component_create(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can add components.")
        return redirect("dashboard")

    if request.method == "POST":
        form = ComponentForm(request.POST)
        if form.is_valid():
            form.save()
            cache.delete("inventory_categories_v1")
            cache.delete("api_components_v1")
            messages.success(request, "Component added.")
            return redirect("admin_components")
    else:
        form = ComponentForm()
    return render(request, "admin/component_form.html", {"form": form, "title": "Add Component"})


@login_required
def admin_component_edit(request, pk):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can edit components.")
        return redirect("dashboard")

    component = get_object_or_404(Component, pk=pk)
    if request.method == "POST":
        form = ComponentForm(request.POST, instance=component)
        if form.is_valid():
            form.save()
            cache.delete("inventory_categories_v1")
            cache.delete("api_components_v1")
            messages.success(request, "Component updated.")
            return redirect("admin_components")
    else:
        form = ComponentForm(instance=component)
    return render(request, "admin/component_form.html", {"form": form, "title": "Edit Component"})


@login_required
def admin_component_delete(request, pk):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        messages.error(request, "Only lab admin can delete components.")
        return redirect("dashboard")

    component = get_object_or_404(Component, pk=pk)
    if request.method == "POST":
        try:
            component.delete()
            cache.delete("inventory_categories_v1")
            cache.delete("api_components_v1")
        except ProtectedError:
            messages.error(
                request,
                "Component cannot be deleted because it is referenced in borrow history. Set stock to zero instead.",
            )
            return redirect("admin_components")
        messages.warning(request, "Component removed.")
        return redirect("admin_components")
    return render(request, "admin/component_confirm_delete.html", {"component": component})


@login_required
def admin_import_excel(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return JsonResponse({"error": "Admin role required."}, status=403)
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    upload = request.FILES.get("file") or request.FILES.get("excel")
    if not upload:
        return JsonResponse({"error": "No Excel file provided."}, status=400)
    filename = (getattr(upload, "name", "") or "").lower()
    if not filename.endswith((".csv", ".xlsx")):
        return JsonResponse({"error": "Invalid file"}, status=400)

    try:
        result = excel_service.import_components_from_excel(upload)
    except excel_service.ExcelImportError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception:
        return JsonResponse({"error": "Import failed. Check file format."}, status=500)

    cache.delete("inventory_categories_v1")
    cache.delete("api_components_v1")
    return JsonResponse({"status": "success", "created": result["created"], "updated": result["updated"]})


@login_required
def admin_export_excel(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return JsonResponse({"error": "Admin role required."}, status=403)
    if request.method != "GET":
        return JsonResponse({"error": "GET required."}, status=405)

    data, filename = excel_service.export_inventory_and_requests()
    response = HttpResponse(
        data,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
