from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from users.models import Profile


def make_user(username: str, role: str, email: str) -> User:
    user = User.objects.create_user(username=username, password="pass1234", email=email)
    profile = user.profile
    profile.role = role
    profile.full_name = "Sample Person"
    profile.save(update_fields=["role", "full_name"])
    return user


class AuthIdentityAndCacheTests(TestCase):
    def test_login_accepts_email_identity(self):
        user = make_user("mail_login_user", Profile.ROLE_STUDENT, "mail.login@am.students.amrita.edu")

        response = self.client.post(
            reverse("login"),
            {"username": user.email, "password": "pass1234"},
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))

    def test_authenticated_html_response_has_no_store_headers(self):
        user = make_user("cache_user", Profile.ROLE_STUDENT, "cache.user@am.students.amrita.edu")
        self.client.login(username=user.username, password="pass1234")

        response = self.client.get(reverse("student_dashboard"), secure=True)

        self.assertEqual(response.status_code, 200)
        cache_control = response.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("no-cache", cache_control)
