from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render

from requests_app.models import BorrowRequest, BorrowRequestItem
from users.models import Profile, Group, GroupMember
from .forms import ComponentForm
from .models import CartItem, Component


def _require_role(user, role):
    profile = getattr(user, "profile", None)
    return profile and profile.role == role


def _is_borrower(user):
    profile = getattr(user, "profile", None)
    return profile and profile.role in (Profile.ROLE_STUDENT, Profile.ROLE_FACULTY)


def _ensure_group(user):
    """
    Ensure a Group and membership exists for the user's profile.group_id.
    Returns (group, status_ok).
    """
    profile = getattr(user, "profile", None)
    if not profile or not profile.group_id:
        return None, False
    group, created = Group.objects.get_or_create(
        code=profile.group_id,
        defaults={
            "faculty": User.objects.filter(username=profile.faculty_incharge).first()
            if profile.faculty_incharge
            else None
        },
    )
    # attach faculty if not set
    if not group.faculty and profile.faculty_incharge:
        fac = User.objects.filter(username=profile.faculty_incharge).first()
        if fac:
            group.faculty = fac
            group.save(update_fields=["faculty"])
    # ensure membership
    GroupMember.objects.get_or_create(group=group, user=user, defaults={"role": GroupMember.ROLE_MEMBER})
    return group, group.status == Group.STATUS_APPROVED


@login_required
def student_dashboard(request):
    if not _is_borrower(request.user):
        return redirect("dashboard")

    group, is_approved = _ensure_group(request.user)

    category_filter = request.GET.get("category", "")
    components = Component.objects.all()
    if category_filter:
        components = components.filter(category=category_filter)

    categories = Component.objects.values_list("category", flat=True).distinct()
    return render(
        request,
        "student/dashboard.html",
        {
            "components": components,
            "categories": categories,
            "selected_category": category_filter,
            "group_status": group.status if group else None,
            "group": group,
            "can_borrow": bool(is_approved),
        },
    )


# ---------------- Admin inventory management ----------------
@login_required
def admin_components(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
        return redirect("dashboard")

    category_filter = request.GET.get("category", "")
    components = Component.objects.all().order_by("name")
    if category_filter:
        components = components.filter(category=category_filter)
    categories = Component.objects.values_list("category", flat=True).distinct()
    return render(
        request,
        "admin/components.html",
        {"components": components, "categories": categories, "selected_category": category_filter},
    )


@login_required
def admin_component_create(request):
    if not _require_role(request.user, Profile.ROLE_ADMIN):
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
        return redirect("dashboard")

    component = get_object_or_404(Component, pk=pk)
    if request.method == "POST":
        component.delete()
        messages.warning(request, "Component removed.")
        return redirect("admin_components")
    return render(request, "admin/component_confirm_delete.html", {"component": component})


@login_required
def add_to_cart(request, component_id):
    if request.method != "POST" or not _is_borrower(request.user):
        return redirect("student_dashboard")

    group, is_approved = _ensure_group(request.user)
    if not is_approved:
        messages.error(request, "Your group is not approved by faculty/admin yet.")
        return redirect("student_dashboard")

    quantity = int(request.POST.get("quantity", 0))
    component = get_object_or_404(Component, id=component_id)

    if quantity <= 0:
        messages.error(request, "Quantity must be greater than zero.")
        return redirect("student_dashboard")

    with transaction.atomic():
        component = Component.objects.select_for_update().get(id=component.id)
        limit = component.student_limit if request.user.profile.role == Profile.ROLE_STUDENT else component.faculty_limit
        if limit and quantity > limit:
            messages.error(request, f"Limit per {request.user.profile.role}: {limit}.")
            return redirect("student_dashboard")

        if component.available_stock < quantity:
            messages.error(request, "Requested quantity exceeds available stock.")
            return redirect("student_dashboard")

        cart_item, created = CartItem.objects.select_for_update().get_or_create(
            student=request.user, component=component, defaults={"quantity": quantity}
        )
        if not created:
            # accumulate quantity while respecting stock
            if component.available_stock < quantity + cart_item.quantity:
                messages.error(request, "Not enough stock to increase quantity.")
                return redirect("student_dashboard")
            if limit and (quantity + cart_item.quantity) > limit:
                messages.error(
                    request,
                    f"Limit per {request.user.profile.role}: {limit}",
                )
                return redirect("student_dashboard")
            cart_item.quantity = F("quantity") + quantity
            cart_item.save()
            cart_item.refresh_from_db()

        component.available_stock = F("available_stock") - quantity
        component.save()

    messages.success(request, f"Added {quantity} x {component.name} to cart.")
    return redirect("student_dashboard")


@login_required
def view_cart(request):
    if not _is_borrower(request.user):
        return redirect("dashboard")

    cart_items = CartItem.objects.filter(student=request.user, slip_generated=False)
    faculties = Profile.objects.filter(role=Profile.ROLE_FACULTY)
    return render(request, "student/cart.html", {"cart_items": cart_items, "faculties": faculties})


@login_required
def remove_cart_item(request, item_id):
    if not _is_borrower(request.user):
        return redirect("dashboard")

    item = get_object_or_404(CartItem, id=item_id, student=request.user)
    with transaction.atomic():
        component = Component.objects.select_for_update().get(id=item.component_id)
        component.available_stock = F("available_stock") + item.quantity
        component.save()
        item.delete()
    messages.info(request, "Item removed from cart.")
    return redirect("view_cart")


@login_required
def generate_slip(request):
    if request.method != "POST" or not _is_borrower(request.user):
        return redirect("view_cart")

    group, is_approved = _ensure_group(request.user)
    if not is_approved:
        messages.error(request, "Your group is not approved by faculty/admin yet.")
        return redirect("view_cart")

    cart_items = list(CartItem.objects.filter(student=request.user, slip_generated=False))
    if not cart_items:
        messages.error(request, "Your cart is empty.")
        return redirect("view_cart")

    faculty_id = request.POST.get("faculty")
    counsellor = request.POST.get("counsellor", "").strip()
    faculty_user = None
    if faculty_id:
        faculty_profile = get_object_or_404(Profile, id=faculty_id, role=Profile.ROLE_FACULTY)
        faculty_user = faculty_profile.user

    if not counsellor:
        messages.error(request, "Counsellor name is required.")
        return redirect("view_cart")

    with transaction.atomic():
        borrow_request = BorrowRequest.objects.create(
            student=request.user, faculty=faculty_user, counsellor=counsellor, group=group
        )

        for item in cart_items:
            BorrowRequestItem.objects.create(
                request=borrow_request, component=item.component, quantity=item.quantity
            )
            item.slip_generated = True
            item.delete()

    messages.success(request, "Borrow slip generated and cart cleared.")
    # In a production setup, trigger PDF generation + email here.
    return redirect("student_requests")


@login_required
def student_requests(request):
    if not _is_borrower(request.user):
        return redirect("dashboard")

    slips = BorrowRequest.objects.filter(
        student=request.user, status=BorrowRequest.STATUS_APPROVED
    ).select_related("faculty")
    return render(request, "student/requests.html", {"slips": slips})
