from django.db import transaction
from django.utils import timezone

from inventory.models import GroupCartLock, Reservation
from requests_app.models import BorrowAction, BorrowItem, BorrowRequest
from users.models import GroupMember, Profile


class CartAccessError(Exception):
    """Raised when a user cannot access the current group cart."""


def _lock_group_cart(group, user, expires_at):
    lock = GroupCartLock.objects.select_for_update().filter(group=group).first()
    now = timezone.now()
    if lock and lock.is_active(now) and lock.locked_by_id != user.id:
        raise CartAccessError("Another group member is currently managing the shared cart.")
    if lock:
        lock.locked_by = user
        lock.expires_at = expires_at
        lock.save(update_fields=["locked_by", "locked_at", "expires_at"])
        return lock
    return GroupCartLock.objects.create(group=group, locked_by=user, expires_at=expires_at)


def assert_group_cart_access(group, user):
    if not group:
        return
    now = timezone.now()
    lock = GroupCartLock.objects.select_for_update().filter(group=group).first()
    if not lock:
        return
    if not lock.is_active(now):
        lock.delete()
        return
    if lock.locked_by_id != user.id:
        raise CartAccessError("Another group member is currently managing the shared cart.")


def sync_group_cart_lock(group, user, reservations):
    if not group:
        return
    reservation_list = list(reservations)
    if not reservation_list:
        GroupCartLock.objects.filter(group=group).delete()
        return
    expires_at = max(res.expires_at for res in reservation_list)
    _lock_group_cart(group, user, expires_at)


def create_borrow_request_from_cart(*, actor, group, project_title):
    profile = getattr(actor, "profile", None)
    role = getattr(profile, "role", "")
    if role not in (Profile.ROLE_STUDENT, Profile.ROLE_FACULTY):
        raise CartAccessError("Only borrower roles can generate slips.")

    with transaction.atomic():
        if role == Profile.ROLE_STUDENT:
            if not group:
                raise CartAccessError("Students must belong to an approved group before borrowing.")
            locked_group = type(group).objects.select_for_update().get(id=group.id)
            if locked_group.status != locked_group.STATUS_APPROVED:
                raise CartAccessError("Group pending faculty approval. Borrowing is locked until approval.")
            assert_group_cart_access(locked_group, actor)
            member_ids = list(
                GroupMember.objects.filter(group=locked_group).values_list("user_id", flat=True)
            )
            reservations = list(
                Reservation.objects.select_for_update()
                .filter(user_id__in=member_ids, is_active=True)
                .select_related("component", "user")
                .order_by("reserved_at", "id")
            )
            faculty_user = locked_group.faculty
            if not faculty_user:
                raise CartAccessError("Your group does not have an assigned faculty in-charge.")
        else:
            locked_group = None
            reservations = list(
                Reservation.objects.select_for_update()
                .filter(user=actor, is_active=True)
                .select_related("component", "user")
                .order_by("reserved_at", "id")
            )
            faculty_user = actor

        if not reservations:
            raise CartAccessError("Your cart is empty or reservations expired.")

        now = timezone.now()
        expired = [res for res in reservations if res.expires_at <= now or not res.is_active]
        if expired:
            for reservation in expired:
                reservation.expire_and_release()
            raise CartAccessError("Some reservations expired before submission. Refresh the cart and try again.")

        first_reserved_at = reservations[0].reserved_at
        borrow_request = BorrowRequest.objects.create(
            user=actor,
            faculty=faculty_user,
            group=locked_group,
            project_title=project_title,
            cart_locked_at=first_reserved_at,
            status=BorrowRequest.STATUS_PENDING,
        )
        borrow_request.set_default_due()
        borrow_request.save(update_fields=["due_date"])
        BorrowAction.objects.create(
            borrow_request=borrow_request,
            action=BorrowAction.ACTION_CREATED,
            performed_by=actor,
        )

        for reservation in reservations:
            BorrowItem.objects.create(
                borrow_request=borrow_request,
                component=reservation.component,
                quantity=reservation.quantity,
            )
            reservation.delete()

        if locked_group:
            GroupCartLock.objects.filter(group=locked_group).delete()

        return borrow_request
