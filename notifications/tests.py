from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from requests_app.models import BorrowRequest
from users.models import Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(
        username=username,
        password="pass1234",
        email=f"{username}@example.com",
    )
    profile = user.profile
    profile.role = role
    profile.full_name = username.title()
    profile.save(update_fields=["role", "full_name"])
    return user


class NotificationCenterTests(TestCase):
    def setUp(self):
        self.admin = make_user("notif_admin", Profile.ROLE_ADMIN)
        self.faculty = make_user("notif_faculty", Profile.ROLE_FACULTY)
        self.student = make_user("notif_student", Profile.ROLE_STUDENT)

    def test_admin_due_today_shows_collected_or_active_items_only(self):
        issued = BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            status=BorrowRequest.STATUS_ISSUED,
            due_date=date.today(),
        )
        BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            status=BorrowRequest.STATUS_APPROVED,
            due_date=date.today(),
        )

        self.client.login(username=self.admin.username, password="pass1234")
        response = self.client.get(reverse("notifications"), secure=True)

        due_today = list(response.context["due_today"])
        self.assertEqual([row.id for row in due_today], [issued.id])

    def test_faculty_due_today_ignores_not_yet_collected_requests(self):
        issued = BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            status=BorrowRequest.STATUS_ISSUED,
            due_date=date.today(),
        )
        BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            status=BorrowRequest.STATUS_APPROVED,
            due_date=date.today(),
        )

        self.client.login(username=self.faculty.username, password="pass1234")
        response = self.client.get(reverse("notifications"), secure=True)

        my_due = list(response.context["my_due"])
        self.assertEqual([row.id for row in my_due], [issued.id])
