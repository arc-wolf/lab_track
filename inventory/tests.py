from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from inventory.models import Component, GroupCartLock, Reservation
from inventory.services.cart_service import CartAccessError, create_borrow_request_from_cart
from requests_app.models import BorrowRequest
from users.models import Group, GroupMember, Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="pass123")
    profile = user.profile
    profile.role = role
    profile.group_id = ""
    profile.save(update_fields=["role", "group_id"])
    return user


class CartServiceTests(TestCase):
    def setUp(self):
        self.faculty = make_user("faculty_cart", Profile.ROLE_FACULTY)
        self.student_a = make_user("student_a", Profile.ROLE_STUDENT)
        self.student_b = make_user("student_b", Profile.ROLE_STUDENT)
        self.group = Group.objects.create(
            code="LOCK100",
            name="Lock Team",
            faculty=self.faculty,
            status=Group.STATUS_APPROVED,
        )
        GroupMember.objects.create(group=self.group, user=self.student_a, role=GroupMember.ROLE_LEADER)
        GroupMember.objects.create(group=self.group, user=self.student_b, role=GroupMember.ROLE_MEMBER)
        self.student_a.profile.group_id = self.group.code
        self.student_a.profile.save(update_fields=["group_id"])
        self.student_b.profile.group_id = self.group.code
        self.student_b.profile.save(update_fields=["group_id"])
        self.component = Component.objects.create(
            name="Sensor Board",
            category="Sensors",
            total_stock=5,
            available_stock=5,
        )

    def test_group_cart_lock_blocks_other_member_submission(self):
        Reservation.objects.create(
            user=self.student_a,
            component=self.component,
            quantity=1,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        GroupCartLock.objects.create(
            group=self.group,
            locked_by=self.student_a,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        with self.assertRaisesMessage(CartAccessError, "Another group member is currently managing"):
            create_borrow_request_from_cart(
                actor=self.student_b,
                group=self.group,
                project_title="Blocked submission",
            )

    def test_create_borrow_request_consumes_group_reservations(self):
        Reservation.objects.create(
            user=self.student_a,
            component=self.component,
            quantity=2,
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        GroupCartLock.objects.create(
            group=self.group,
            locked_by=self.student_a,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        borrow_request = create_borrow_request_from_cart(
            actor=self.student_a,
            group=self.group,
            project_title="Shared cart request",
        )

        self.assertEqual(borrow_request.status, BorrowRequest.STATUS_PENDING)
        self.assertEqual(borrow_request.faculty, self.faculty)
        self.assertEqual(borrow_request.group, self.group)
        self.assertFalse(Reservation.objects.filter(user=self.student_a, is_active=True).exists())
        self.assertFalse(GroupCartLock.objects.filter(group=self.group).exists())
        self.assertEqual(borrow_request.items.count(), 1)

    def test_expired_reservation_is_rejected_before_slip_creation(self):
        Reservation.objects.create(
            user=self.student_a,
            component=self.component,
            quantity=1,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        with self.assertRaisesMessage(CartAccessError, "Some reservations expired before submission"):
            create_borrow_request_from_cart(
                actor=self.student_a,
                group=self.group,
                project_title="Expired request",
            )
