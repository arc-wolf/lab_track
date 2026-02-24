from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from users.models import Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="pass")
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


class DashboardRedirectTests(TestCase):
    def test_admin_user_redirects_to_admin_dashboard(self):
        user = make_user("admin", Profile.ROLE_ADMIN)
        self.client.login(username="admin", password="pass")

        response = self.client.get(reverse("dashboard"), secure=True)

        self.assertRedirects(response, reverse("admin_dashboard"), fetch_redirect_response=False)

    def test_faculty_user_redirects_to_faculty_dashboard(self):
        user = make_user("faculty", Profile.ROLE_FACULTY)
        self.client.login(username="faculty", password="pass")

        response = self.client.get(reverse("dashboard"), secure=True)

        self.assertRedirects(response, reverse("faculty_dashboard"), fetch_redirect_response=False)

    def test_student_user_redirects_to_student_dashboard(self):
        user = make_user("student", Profile.ROLE_STUDENT)
        self.client.login(username="student", password="pass")

        response = self.client.get(reverse("dashboard"), secure=True)

        self.assertRedirects(response, reverse("student_dashboard"), fetch_redirect_response=False)
