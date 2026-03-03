from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from requests_app.models import BorrowRequest, BorrowItem
from users.models import Group, GroupMember, Profile
from .forms import ComponentForm
from .models import Component, Reservation


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
            Profile.objects.filter(role=Profile.ROLE_FACULTY, user__username=profile.faculty_incharge)
            .select_related("user")
            .first()
        )
        if not faculty:
            faculty = (
                Profile.objects.filter(role=Profile.ROLE_FACULTY, user__email__iexact=profile.faculty_incharge)
                .select_related("user")
                .first()
            )
        if not faculty:
            faculty = (
                Profile.objects.filter(role=Profile.ROLE_FACULTY, full_name__iexact=profile.faculty_incharge)
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
    components = Component.objects.all()
    if category_filter:
        components = components.filter(category=category_filter)
    if search_query:
        components = components.filter(name__icontains=search_query)

    categories = Component.objects.values_list("category", flat=True).distinct()

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
            },
            "search_query": search_query,
            "shared_mode": bool(request.user.profile.role == Profile.ROLE_STUDENT and group),
            "group_member_count": len(member_ids) if member_ids else 1,
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

    if quantity <= 0:
        messages.error(request, "Quantity must be greater than zero.")
        return redirect("student_dashboard")

    with transaction.atomic():
        locked = Component.objects.select_for_update().get(id=component.id)
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
            "shared_mode": bool(request.user.profile.role == Profile.ROLE_STUDENT and group),
            "is_faculty_user": request.user.profile.role == Profile.ROLE_FACULTY,
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
        res.expire_and_release()
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

    is_faculty_user = request.user.profile.role == Profile.ROLE_FACULTY
    faculty_id = request.POST.get("faculty", "").strip()
    project_title = request.POST.get("project_title", "").strip()
    if not is_faculty_user and not faculty_id:
        messages.error(request, "Select a faculty in-charge.")
        return redirect("view_cart")
    if not project_title:
        messages.error(request, "Project title is required.")
        return redirect("view_cart")

    faculty_user = request.user if is_faculty_user else None
    if not is_faculty_user:
        try:
            if faculty_id:
                faculty_user = Profile.objects.select_related("user").get(
                    id=int(faculty_id), role=Profile.ROLE_FACULTY
                ).user
        except (Profile.DoesNotExist, ValueError):
            faculty_user = None
    if not faculty_user:
        messages.error(request, "Selected faculty not found.")
        return redirect("view_cart")
    if group and group.faculty_id and group.faculty_id != faculty_user.id:
        messages.error(request, "Selected faculty does not match your approved group in-charge.")
        return redirect("view_cart")

    with transaction.atomic():
        first_reserved_at = min(res.reserved_at for res in reservations)
        borrow_request = BorrowRequest.objects.create(
            user=request.user,
            faculty=faculty_user,
            group=group,
            project_title=project_title,
            cart_locked_at=first_reserved_at,
            status=BorrowRequest.STATUS_PENDING,
        )
        borrow_request.set_default_due()
        borrow_request.save(update_fields=["due_date"])
        from requests_app.models import BorrowAction
        BorrowAction.objects.create(
            borrow_request=borrow_request,
            action=BorrowAction.ACTION_CREATED,
            performed_by=request.user,
        )

        for res in reservations:
            BorrowItem.objects.create(
                borrow_request=borrow_request,
                component=res.component,
                quantity=res.quantity,
            )
            # Reservation is consumed by request creation; remove row to avoid
            # stale inactive duplicates and keep cart table compact.
            res.delete()

    messages.success(request, "Borrow slip generated. Awaiting approval.")
    return redirect("student_requests")


@login_required
def student_requests(request):
    if not _is_borrower(request.user):
        messages.error(request, "You do not have access to request history.")
        return redirect("dashboard")

    group, _ = _ensure_group(request.user)
    if request.user.profile.role == Profile.ROLE_STUDENT and group:
        slips_qs = BorrowRequest.objects.filter(group=group)
    else:
        slips_qs = BorrowRequest.objects.filter(user=request.user)
    slips = (
        slips_qs.select_related("user", "faculty")
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
        components = components.filter(available_stock__lte=2)
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
        except ProtectedError:
            messages.error(
                request,
                "Component cannot be deleted because it is referenced in borrow history. Set stock to zero instead.",
            )
            return redirect("admin_components")
        messages.warning(request, "Component removed.")
        return redirect("admin_components")
    return render(request, "admin/component_confirm_delete.html", {"component": component})
