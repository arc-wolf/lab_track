from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from requests_app.models import BorrowRequest
from users.models import Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="pass", email=f"{username}@example.com")
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


class FacultyDashboardMetricTests(TestCase):
    def test_awaiting_return_counts_issued_requests(self):
        faculty = make_user("fac_metric", Profile.ROLE_FACULTY)
        student = make_user("stu_metric", Profile.ROLE_STUDENT)

        BorrowRequest.objects.create(
            user=student,
            faculty=faculty,
            status=BorrowRequest.STATUS_ISSUED,
            project_title="Issued slip",
        )

        self.client.login(username="fac_metric", password="pass")
        response = self.client.get(reverse("faculty_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["awaiting_return"], 1)

