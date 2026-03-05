from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from inventory.models import Component
from requests_app.models import BorrowAction, BorrowRequest, BorrowRequestItem
from users.models import Group, GroupMember, Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="pass")
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SlipActionTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin", Profile.ROLE_ADMIN)
        self.faculty = make_user("faculty", Profile.ROLE_FACULTY)
        self.student = make_user("student", Profile.ROLE_STUDENT)

        self.component = Component.objects.create(
            name="Oscilloscope", category="Lab Gear", total_stock=10, available_stock=5
        )

    def _make_slip(self, status=BorrowRequest.STATUS_PENDING, faculty=None, quantity=2):
        slip = BorrowRequest.objects.create(
            student=self.student,
            faculty=faculty,
            counsellor="Advisor",
        )
        slip.status = status
        slip.save(update_fields=["status"])
        BorrowRequestItem.objects.create(request=slip, component=self.component, quantity=quantity)
        return slip

    def test_faculty_cannot_approve_other_faculty_slip(self):
        other_faculty = make_user("other", Profile.ROLE_FACULTY)
        slip = self._make_slip(faculty=other_faculty)
        self.client.login(username="faculty", password="pass")

        response = self.client.post(reverse("approve_slip", args=[slip.id]), secure=True)

        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_PENDING)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_admin_approves_pending_slip(self):
        slip = self._make_slip(faculty=self.faculty)
        self.client.login(username="admin", password="pass")

        response = self.client.post(reverse("approve_slip", args=[slip.id]), secure=True)

        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_APPROVED)
        self.assertRedirects(response, reverse("admin_requests_console"), fetch_redirect_response=False)

    def test_mark_returned_restores_stock(self):
        slip = self._make_slip(status=BorrowRequest.STATUS_APPROVED, faculty=self.faculty, quantity=3)
        self.component.available_stock = 2
        self.component.save(update_fields=["available_stock"])
        self.client.login(username="admin", password="pass")

        before = timezone.now()
        response = self.client.post(
            reverse("mark_returned", args=[slip.id]), {"condition": "Good"}, secure=True
        )

        self.component.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_RETURNED)
        self.assertEqual(self.component.available_stock, 5)
        self.assertEqual(slip.return_condition, "Good")
        self.assertIsNotNone(slip.return_time)
        self.assertGreaterEqual(slip.return_time, before)
        self.assertRedirects(response, reverse("admin_requests_console"), fetch_redirect_response=False)

    def test_terminate_pending_slip_restores_stock(self):
        slip = self._make_slip(status=BorrowRequest.STATUS_PENDING, faculty=self.faculty, quantity=4)
        self.component.available_stock = 3
        self.component.save(update_fields=["available_stock"])
        self.client.login(username="admin", password="pass")

        response = self.client.post(reverse("terminate_slip", args=[slip.id]), secure=True)

        self.component.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_TERMINATED)
        self.assertEqual(self.component.available_stock, 7)
        self.assertRedirects(response, reverse("admin_requests_console"), fetch_redirect_response=False)

    def test_mark_returned_allows_penalty_state(self):
        slip = self._make_slip(status=BorrowRequest.STATUS_PENALTY, faculty=self.faculty, quantity=3)
        self.component.available_stock = 2
        self.component.save(update_fields=["available_stock"])
        self.client.login(username="admin", password="pass")

        response = self.client.post(
            reverse("mark_returned", args=[slip.id]), {"condition": "Service needed"}, secure=True
        )

        self.component.refresh_from_db()
        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_RETURNED)
        self.assertEqual(self.component.available_stock, 5)
        self.assertRedirects(response, reverse("admin_requests_console"), fetch_redirect_response=False)

    def test_student_group_member_can_download_group_slip_pdf(self):
        teammate = make_user("teammate", Profile.ROLE_STUDENT)
        group = Group.objects.create(code="GTEAM1", name="Team One", faculty=self.faculty)
        GroupMember.objects.create(group=group, user=self.student, role=GroupMember.ROLE_LEADER)
        GroupMember.objects.create(group=group, user=teammate, role=GroupMember.ROLE_MEMBER)
        self.student.profile.group_id = group.code
        self.student.profile.save(update_fields=["group_id"])
        teammate.profile.group_id = group.code
        teammate.profile.save(update_fields=["group_id"])

        slip = self._make_slip(status=BorrowRequest.STATUS_PENDING, faculty=self.faculty, quantity=1)
        slip.group = group
        slip.save(update_fields=["group"])

        self.client.login(username="teammate", password="pass")
        response = self.client.get(reverse("download_slip", args=[slip.id]), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_mark_penalty_uses_component_specific_per_day_fine(self):
        self.component.fine_per_day = 25
        self.component.save(update_fields=["fine_per_day"])
        slip = self._make_slip(status=BorrowRequest.STATUS_OVERDUE, faculty=self.faculty, quantity=2)
        slip.due_date = timezone.now().date() - timedelta(days=5)
        slip.save(update_fields=["due_date"])
        self.client.login(username="admin", password="pass")

        response = self.client.post(reverse("mark_penalty", args=[slip.id]), secure=True)

        slip.refresh_from_db()
        self.assertEqual(slip.status, BorrowRequest.STATUS_PENALTY)
        action = BorrowAction.objects.filter(
            borrow_request=slip,
            action=BorrowAction.ACTION_PENALTY,
        ).first()
        self.assertIsNotNone(action)
        self.assertIn("INR 25", action.note)
        self.assertRedirects(response, reverse("admin_requests_console"), fetch_redirect_response=False)
