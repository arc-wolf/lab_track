from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Component
from requests_app.models import BorrowRequest
from users.models import AuditLog, Profile
from users.services.audit_service import record_audit_log


class AuditConsoleUITests(TestCase):

    def setUp(self):
        self.client = Client()

        # Admin User
        self.admin = User.objects.create_user("admin_ui_test", password="Password123!", email="admin_ui_test@example.com")
        self.admin.profile.role = Profile.ROLE_ADMIN
        self.admin.profile.full_name = "Admin UI Tester"
        self.admin.profile.save()

        # Student User
        self.student = User.objects.create_user("student_ui_test", password="Password123!", email="student_ui_test@example.com")
        self.student.profile.role = Profile.ROLE_STUDENT
        self.student.profile.full_name = "Student UI Tester"
        self.student.profile.save()

        # Sample Audit Entry
        record_audit_log(
            action="APPROVE_SLIP",
            target_object="BorrowRequest #101",
            user=self.admin,
            details="Approved obstacle bot borrow slip",
        )

    def test_audit_console_template_rendering(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_audit_console"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/audit_console.html")
        content = resp.content.decode("utf-8")

        # Verify page elements & headers
        self.assertIn("System Audit Trail", content)
        self.assertIn("APPROVE_SLIP", content)
        self.assertIn("BorrowRequest #101", content)
        self.assertIn("admin_ui_test", content)
        self.assertIn("Export History CSV", content)
        self.assertIn("Export Stock CSV", content)

    def test_csv_export_file_download(self):
        self.client.force_login(self.admin)

        # Inventory CSV
        resp = self.client.get(reverse("export_inventory_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn('attachment; filename="labtrack_inventory.csv"', resp["Content-Disposition"])

        # Borrow History CSV
        resp = self.client.get(reverse("export_borrow_history_csv"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn('attachment; filename="labtrack_borrow_history.csv"', resp["Content-Disposition"])

    def test_audit_console_search_and_filtering(self):
        self.client.force_login(self.admin)

        record_audit_log(
            action="REJECT_SLIP",
            target_object="BorrowRequest #202",
            user=self.admin,
            details="Rejected due to missing faculty signature",
        )

        # Filter by action=REJECT_SLIP
        resp = self.client.get(reverse("admin_audit_console") + "?action=REJECT_SLIP")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("BorrowRequest #202", content)
        self.assertNotIn("BorrowRequest #101", content)

        # Search by query ?q=missing
        resp = self.client.get(reverse("admin_audit_console") + "?q=missing")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("BorrowRequest #202", content)

