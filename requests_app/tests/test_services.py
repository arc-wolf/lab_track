from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from inventory.models import Component, Reservation
from inventory.services import (
    ReservationError,
    add_to_cart_reservation,
    remove_cart_reservation,
    create_borrow_request_from_cart,
    clean_expired_reservations,
)
from requests_app.models import BorrowRequest, BorrowItem
from requests_app.services.borrow_service import (
    BorrowFlowError,
    approve_request,
    mark_request_issued,
    mark_request_returned,
    reject_request,
)
from users.models import Profile


class ServiceLayerTestCase(TestCase):
    def setUp(self):
        self.student_user = User.objects.create_user(
            username="test_student",
            email="test_student@am.students.amrita.edu",
            password="Password123!",
        )
        self.student_profile, _ = Profile.objects.get_or_create(
            user=self.student_user,
            defaults={"role": Profile.ROLE_STUDENT, "full_name": "Test Student"},
        )
        self.student_profile.role = Profile.ROLE_STUDENT
        self.student_profile.full_name = "Test Student"
        self.student_profile.save()

        self.faculty_user = User.objects.create_user(
            username="test_faculty",
            email="test_faculty@am.amrita.edu",
            password="Password123!",
        )
        self.faculty_profile, _ = Profile.objects.get_or_create(
            user=self.faculty_user,
            defaults={"role": Profile.ROLE_FACULTY, "full_name": "Test Faculty"},
        )
        self.faculty_profile.role = Profile.ROLE_FACULTY
        self.faculty_profile.full_name = "Test Faculty"
        self.faculty_profile.save()

        self.admin_user = User.objects.create_user(
            username="test_admin",
            email="admin@am.amrita.edu",
            password="Password123!",
        )
        self.admin_profile, _ = Profile.objects.get_or_create(
            user=self.admin_user,
            defaults={"role": Profile.ROLE_ADMIN, "full_name": "Lab Admin"},
        )
        self.admin_profile.role = Profile.ROLE_ADMIN
        self.admin_profile.full_name = "Lab Admin"
        self.admin_profile.save()

        self.component = Component.objects.create(
            name="Arduino Uno R3",
            category="Microcontrollers",
            total_stock=10,
            available_stock=10,
            student_limit=5,
            faculty_limit=10,
        )

    def test_add_to_cart_reservation_success(self):
        res, final_qty, is_new = add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=2,
        )
        self.assertTrue(is_new)
        self.assertEqual(final_qty, 2)
        self.component.refresh_from_db()
        self.assertEqual(self.component.available_stock, 8)

    def test_add_to_cart_exceeds_stock_raises_error(self):
        with self.assertRaises(ReservationError):
            add_to_cart_reservation(
                user=self.student_user,
                component=self.component,
                quantity=15,
            )

    def test_remove_cart_reservation_restores_stock(self):
        res, _, _ = add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=3,
        )
        self.component.refresh_from_db()
        self.assertEqual(self.component.available_stock, 7)

        remove_cart_reservation(user=self.student_user, reservation_id=res.id)
        self.component.refresh_from_db()
        self.assertEqual(self.component.available_stock, 10)

    def test_clean_expired_reservations(self):
        res, _, _ = add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=2,
        )
        res.expires_at = timezone.now() - timedelta(minutes=1)
        res.save(update_fields=["expires_at"])

        clean_expired_reservations(user=self.student_user)
        self.component.refresh_from_db()
        self.assertEqual(self.component.available_stock, 10)
        res.refresh_from_db()
        self.assertFalse(res.is_active)

    def test_create_borrow_request_from_cart(self):
        add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=2,
        )
        borrow_req = create_borrow_request_from_cart(
            user=self.student_user,
            faculty_user=self.faculty_user,
            project_title="IoT Robot arm",
        )
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_PENDING)
        self.assertEqual(borrow_req.items.count(), 1)
        self.assertEqual(borrow_req.items.first().quantity, 2)

    def test_borrow_service_lifecycle(self):
        add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=2,
        )
        borrow_req = create_borrow_request_from_cart(
            user=self.student_user,
            faculty_user=self.faculty_user,
            project_title="IoT Robot arm",
        )

        approve_request(borrow_req, by_user=self.faculty_user)
        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_APPROVED)

        mark_request_issued(borrow_req, by_user=self.admin_user, note="Collected by Student")
        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_ISSUED)

        mark_request_returned(borrow_req, by_user=self.admin_user, condition="Good condition")
        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_RETURNED)
        self.component.refresh_from_db()
        self.assertEqual(self.component.available_stock, 10)

    def test_invalid_lifecycle_transition_raises_error(self):
        add_to_cart_reservation(
            user=self.student_user,
            component=self.component,
            quantity=2,
        )
        borrow_req = create_borrow_request_from_cart(
            user=self.student_user,
            faculty_user=self.faculty_user,
            project_title="IoT Robot arm",
        )
        with self.assertRaises(BorrowFlowError):
            mark_request_issued(borrow_req, by_user=self.admin_user)
