from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from inventory.models import Component, Reservation
from requests_app.models import BorrowRequest, BorrowItem, BorrowAction
from users.models import Profile


class ReservationError(Exception):
    """Raised when a reservation or cart operation fails validation or stock limits."""


def clean_expired_reservations(user=None, user_ids=None):
    """Expire and release stock for active reservations whose TTL has elapsed."""
    qs = Reservation.objects.filter(is_active=True, expires_at__lte=timezone.now())
    if user_ids is not None:
        qs = qs.filter(user_id__in=user_ids)
    elif user:
        qs = qs.filter(user=user)
    for res in qs.select_related("component"):
        res.expire_and_release()


def add_to_cart_reservation(user, component: Component, quantity: int, member_ids=None):
    """
    Atomically add a component to a user's or team's active cart.
    Deducts available stock and creates or updates a 15-minute reservation.
    """
    if quantity <= 0:
        raise ReservationError("Quantity must be greater than zero.")

    user_role = getattr(getattr(user, "profile", None), "role", Profile.ROLE_STUDENT)

    with transaction.atomic():
        locked = Component.objects.select_for_update().get(id=component.id)
        limit = locked.student_limit if user_role == Profile.ROLE_STUDENT else locked.faculty_limit

        if locked.available_stock < quantity:
            raise ReservationError("Requested quantity exceeds available stock.")

        if user_role == Profile.ROLE_STUDENT and member_ids:
            existing_qs = Reservation.objects.select_for_update().filter(
                user_id__in=member_ids, component=locked, is_active=True
            )
        else:
            existing_qs = Reservation.objects.select_for_update().filter(
                user=user, component=locked, is_active=True
            )

        existing = existing_qs.first()
        if existing:
            new_qty = existing.quantity + quantity
            if limit and new_qty > limit:
                raise ReservationError(f"Limit per user: {limit}.")
            locked.adjust_available(-quantity)
            existing.quantity = new_qty
            existing.expires_at = timezone.now() + timedelta(minutes=15)
            existing.save(update_fields=["quantity", "expires_at"])
            return existing, new_qty, False

        if limit and quantity > limit:
            raise ReservationError(f"Limit per user: {limit}.")

        locked.adjust_available(-quantity)
        res = Reservation.objects.create(
            user=user,
            component=locked,
            quantity=quantity,
            expires_at=timezone.now() + timedelta(minutes=15),
            is_active=True,
        )
        return res, quantity, True


def remove_cart_reservation(user, reservation_id: int, member_ids=None):
    """
    Remove an active reservation and restore available component stock.
    """
    user_role = getattr(getattr(user, "profile", None), "role", Profile.ROLE_STUDENT)
    if user_role == Profile.ROLE_STUDENT and member_ids:
        res = Reservation.objects.filter(id=reservation_id, user_id__in=member_ids, is_active=True).first()
    else:
        res = Reservation.objects.filter(id=reservation_id, user=user, is_active=True).first()

    if not res:
        raise ReservationError("Reservation item not found or already released.")

    with transaction.atomic():
        res.expire_and_release()
    return res


def create_borrow_request_from_cart(user, faculty_user, project_title: str, group=None, member_ids=None):
    """
    Convert active cart reservations into a formal pending BorrowRequest.
    Consumes active reservations and creates BorrowItem records.
    """
    user_role = getattr(getattr(user, "profile", None), "role", Profile.ROLE_STUDENT)
    if user_role == Profile.ROLE_STUDENT and member_ids:
        reservations_qs = Reservation.objects.filter(user_id__in=member_ids, is_active=True)
    else:
        reservations_qs = Reservation.objects.filter(user=user, is_active=True)

    reservations = list(reservations_qs.select_related("component", "user").order_by("reserved_at"))
    if not reservations:
        raise ReservationError("Your cart is empty or reservations have expired.")

    if not project_title:
        raise ReservationError("Project title is required.")

    with transaction.atomic():
        first_reserved_at = min(res.reserved_at for res in reservations)
        borrow_request = BorrowRequest.objects.create(
            user=user,
            faculty=faculty_user,
            group=group,
            project_title=project_title,
            cart_locked_at=first_reserved_at,
            status=BorrowRequest.STATUS_PENDING,
        )
        borrow_request.set_default_due()
        borrow_request.save(update_fields=["due_date"])

        BorrowAction.objects.create(
            borrow_request=borrow_request,
            action=BorrowAction.ACTION_CREATED,
            performed_by=user,
        )

        for res in reservations:
            BorrowItem.objects.create(
                borrow_request=borrow_request,
                component=res.component,
                quantity=res.quantity,
            )
            res.delete()

    return borrow_request
