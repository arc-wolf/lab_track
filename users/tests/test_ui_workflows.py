from datetime import timedelta
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Component, Reservation
from requests_app.models import BorrowItem, BorrowRequest, LabPolicy
from users.models import EmailOTP, Group, GroupMember, Profile


class UIWorkflowIntegrationTests(TestCase):
    """End-to-end UI user journey integration tests simulating browser interactions."""

    def setUp(self):
        self.client = Client()

        # Faculty User
        self.faculty = User.objects.create_user("prof_ui", password="Password123!", email="prof_ui@example.com")
        self.faculty.profile.role = Profile.ROLE_FACULTY
        self.faculty.profile.full_name = "Prof UI Test"
        self.faculty.profile.save()

        # Admin User
        self.admin = User.objects.create_user("admin_ui", password="Password123!", email="admin_ui@example.com")
        self.admin.profile.role = Profile.ROLE_ADMIN
        self.admin.profile.full_name = "Admin UI Test"
        self.admin.profile.save()

        # Components
        self.c1 = Component.objects.create(
            name="Arduino Uno R3",
            category="Microcontrollers",
            total_stock=10,
            available_stock=10,
        )
        self.c2 = Component.objects.create(
            name="Ultrasonic Sensor HC-SR04",
            category="Sensors",
            total_stock=15,
            available_stock=15,
        )

    def test_complete_student_borrow_and_admin_fulfillment_journey(self):
        """Simulate student registration, team creation, cart reservation, slip generation, and admin issue/return."""

        # Step 1: Student Registration Form Submission
        signup_data = {
            "email": "student_journey@am.students.amrita.edu",
            "password1": "Password123!",
            "password2": "Password123!",
            "full_name": "Student Journey",
            "phone": "9876543210",
            "semester": "5",
            "student_class": "ECE-A",
            "group_mode": "create",
            "group_name": "Journey Team",
            "faculty_incharge": str(self.faculty.profile.id),
        }
        resp = self.client.post(reverse("signup"), signup_data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pending_signup_email", self.client.session)

        # Retrieve generated OTP
        otp_rec = EmailOTP.objects.filter(email="student_journey@am.students.amrita.edu", is_used=False).first()
        self.assertIsNotNone(otp_rec)

        # Step 2: OTP Verification & Auto-Login
        otp_data = {"otp": otp_rec.code, "otp_stage": "1"}
        resp = self.client.post(reverse("signup"), otp_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Student user created & logged in
        student = User.objects.get(email="student_journey@am.students.amrita.edu")
        group = Group.objects.filter(code=student.profile.group_id).first()

        # Step 3: Approve Student Group (as Admin)
        group.status = Group.STATUS_APPROVED
        group.save()

        # Step 4: Add Component to Cart
        resp = self.client.post(
            reverse("add_to_cart", args=[self.c1.id]),
            {"quantity": 2},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        # Verify Reservation in database
        self.assertTrue(Reservation.objects.filter(user=student, component=self.c1, is_active=True).exists())

        # Step 5: View Cart Page
        resp = self.client.get(reverse("view_cart"))
        self.assertEqual(resp.status_code, 200)

        # Step 6: Generate Borrow Slip from Cart
        slip_data = {
            "faculty": str(self.faculty.profile.id),
            "project_title": "Automated Obstacle Avoidance Bot",
        }
        resp = self.client.post(reverse("generate_slip"), slip_data, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Verify BorrowRequest created
        borrow_req = BorrowRequest.objects.filter(user=student).first()
        self.assertIsNotNone(borrow_req)
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_PENDING)

        # Step 7: Faculty Login & Slip Approval
        self.client.force_login(self.faculty)
        resp = self.client.post(reverse("approve_slip", args=[borrow_req.id]), follow=True)
        self.assertEqual(resp.status_code, 200)

        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_APPROVED)

        # Step 8: Admin Login & Component Issue
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("mark_issued", args=[borrow_req.id]),
            {"collector_name": "Student Collector"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_ISSUED)

        # Step 9: Download PDF Slip Document
        resp = self.client.get(reverse("download_slip", args=[borrow_req.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

        # Step 10: Admin Component Return & Stock Restoration
        resp = self.client.post(reverse("mark_returned", args=[borrow_req.id]), follow=True)
        self.assertEqual(resp.status_code, 200)

        borrow_req.refresh_from_db()
        self.assertEqual(borrow_req.status, BorrowRequest.STATUS_RETURNED)
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.available_stock, 10)
