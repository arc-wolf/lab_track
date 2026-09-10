from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Component
from requests_app.models import BorrowRequest
from users.models import AuditLog, Profile
from users.services.audit_service import record_audit_log


class AuditAndExportTests(TestCase):

    def setUp(self):
        self.client = Client()

        # Admin
        self.admin = User.objects.create_user("admin_audit", password="Password123!", email="admin_audit@example.com")
        self.admin.profile.role = Profile.ROLE_ADMIN
        self.admin.profile.save()

        # Student
        self.student = User.objects.create_user("student_audit", password="Password123!", email="student_audit@example.com")
        self.student.profile.role = Profile.ROLE_STUDENT
        self.student.profile.save()

        # Component
        self.comp = Component.objects.create(name="Raspberry Pi 4", category="SBC", total_stock=5, available_stock=4)

        # BorrowRequest
        self.req = BorrowRequest.objects.create(user=self.student, project_title="IoT Weather Station")

    def test_record_audit_log_service(self):
        entry = record_audit_log(
            action="TEST_ACTION",
            target_object="Component: Raspberry Pi 4",
            user=self.admin,
            details="Unit test entry",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(entry.action, "TEST_ACTION")

    def test_admin_audit_console_view(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_audit_console"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/audit_console.html")

    def test_export_inventory_csv(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("export_inventory_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("Raspberry Pi 4", resp.content.decode("utf-8"))

    def test_export_borrow_history_csv(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("export_borrow_history_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("IoT Weather Station", resp.content.decode("utf-8"))

    def test_non_admin_denied(self):
        self.client.force_login(self.student)
        resp = self.client.get(reverse("admin_audit_console"))
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get(reverse("export_inventory_csv"))
        self.assertEqual(resp.status_code, 302)
