from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventory.models import Component, Reservation
from requests_app.models import BorrowItem, BorrowRequest, LabPolicy
from users.models import APIToken, Group, GroupMember, Profile


class AllEndpointsCoverageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("ep_admin", password="Password123!", email="ep_admin@example.com")
        self.admin.profile.role = Profile.ROLE_ADMIN
        self.admin.profile.full_name = "Ep Admin"
        self.admin.profile.save()
        self.admin.refresh_from_db()

        self.faculty = User.objects.create_user("ep_faculty", password="Password123!", email="ep_faculty@example.com")
        self.faculty.profile.role = Profile.ROLE_FACULTY
        self.faculty.profile.full_name = "Ep Faculty"
        self.faculty.profile.save()
        self.faculty.refresh_from_db()

        self.student = User.objects.create_user("ep_student", password="Password123!", email="ep_student@example.com")
        self.student.profile.role = Profile.ROLE_STUDENT
        self.student.profile.group_id = "EP_GRP"
        self.student.profile.group_name = "EP Group"
        self.student.profile.save()
        self.student.refresh_from_db()

        self.group = Group.objects.create(
            code="EP_GRP",
            name="EP Group",
            faculty=self.faculty,
            status=Group.STATUS_APPROVED,
        )
        GroupMember.objects.create(group=self.group, user=self.student, role=GroupMember.ROLE_LEADER)

        self.component = Component.objects.create(
            name="EP Component",
            category="Sensors",
            total_stock=10,
            available_stock=8,
        )

        self.reservation = Reservation.objects.create(
            user=self.student,
            component=self.component,
            quantity=2,
            expires_at=timezone.now() + timedelta(minutes=15),
        )

        self.borrow_req = BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            group=self.group,
            project_title="EP Project",
            status=BorrowRequest.STATUS_PENDING,
        )
        BorrowItem.objects.create(borrow_request=self.borrow_req, component=self.component, quantity=2)

        self.admin_token, _ = APIToken.objects.get_or_create(user=self.admin)
        self.student_token, _ = APIToken.objects.get_or_create(user=self.student)

    # 1. Accounts & Authentication Endpoints
    def test_auth_endpoints(self):
        # GET Login
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)

        # GET Signup
        resp = self.client.get(reverse("signup"))
        self.assertEqual(resp.status_code, 200)

        # GET Password Reset
        resp = self.client.get(reverse("password_reset"))
        self.assertEqual(resp.status_code, 200)

        # GET Password Reset Confirm without session -> redirect password_reset
        resp = self.client.get(reverse("password_reset_otp_confirm"))
        self.assertRedirects(resp, reverse("password_reset"))

    # 2. Student & Inventory Endpoints
    def test_student_and_inventory_endpoints(self):
        self.client.force_login(self.student)

        # Root redirect
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)

        # Student Dashboard
        resp = self.client.get(reverse("student_dashboard"))
        self.assertEqual(resp.status_code, 200)

        # View Cart
        resp = self.client.get(reverse("view_cart"))
        self.assertEqual(resp.status_code, 200)

        # Student Requests
        resp = self.client.get(reverse("student_requests"))
        self.assertEqual(resp.status_code, 200, f"Expected 200 but got {resp.status_code}, redirecting to {resp.headers.get('Location')}")

        # Student Group Console
        resp = self.client.get(reverse("student_group_console"))
        self.assertEqual(resp.status_code, 200)

        # Student Profile Console
        resp = self.client.get(reverse("student_profile_console"))
        self.assertEqual(resp.status_code, 200)

    # 3. Faculty Endpoints
    def test_faculty_endpoints(self):
        self.client.force_login(self.faculty)

        # Faculty Dashboard
        resp = self.client.get(reverse("faculty_dashboard"))
        self.assertEqual(resp.status_code, 200)

        # Faculty Profile Console
        resp = self.client.get(reverse("faculty_profile_console"))
        self.assertEqual(resp.status_code, 200)

        # Faculty Groups Management
        resp = self.client.get(reverse("faculty_groups"))
        self.assertEqual(resp.status_code, 200)

    # 4. Admin Consoles & Management Endpoints
    def test_admin_endpoints(self):
        self.client.force_login(self.admin)

        # Admin Dashboard
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 200)

        # Admin Requests Console
        resp = self.client.get(reverse("admin_requests_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Inventory Components
        resp = self.client.get(reverse("admin_components"))
        self.assertEqual(resp.status_code, 200)

        # Admin Component Create Form
        resp = self.client.get(reverse("admin_component_create"))
        self.assertEqual(resp.status_code, 200)

        # Admin Component Edit Form
        resp = self.client.get(reverse("admin_component_edit", args=[self.component.id]))
        self.assertEqual(resp.status_code, 200)

        # Admin Faculty Console
        resp = self.client.get(reverse("admin_faculty_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Component Policy Console
        resp = self.client.get(reverse("admin_component_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Data Console
        resp = self.client.get(reverse("admin_data_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Maintenance Console
        resp = self.client.get(reverse("admin_maintenance_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Reports Console
        resp = self.client.get(reverse("admin_reports_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Groups Console
        resp = self.client.get(reverse("admin_groups"))
        self.assertEqual(resp.status_code, 200)

        # Admin Student Console
        resp = self.client.get(reverse("admin_student_console"))
        self.assertEqual(resp.status_code, 200)

        # Admin Profile Console
        resp = self.client.get(reverse("admin_profile_console"))
        self.assertEqual(resp.status_code, 200)

    # 5. Notifications Center
    def test_notifications_endpoint(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse("notifications"))
        self.assertEqual(resp.status_code, 200)

    # 6. PDF Slip Download Endpoint
    def test_pdf_download_endpoint(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("download_slip", args=[self.borrow_req.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    # 7. Complete API Endpoints Verification
    def test_api_endpoints(self):
        # Health Check (Unauthenticated)
        resp = self.client.get(reverse("api_health_check"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("status", resp.json())

        # Me endpoint
        resp = self.client.get(
            reverse("api_me"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)

        # Components endpoint
        resp = self.client.get(
            reverse("api_components"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)

        # Requests endpoint
        resp = self.client.get(
            reverse("api_borrow_requests"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)

        # Admin Overview
        resp = self.client.get(
            reverse("api_admin_overview"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)

        # Admin Console Map
        resp = self.client.get(
            reverse("api_admin_console_map"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)

        # Admin Policy
        resp = self.client.get(
            reverse("api_admin_policy"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200)
