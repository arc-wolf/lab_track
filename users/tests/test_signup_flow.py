from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User

from users.models import Profile


class SignupFlowTests(TestCase):
    def setUp(self):
        self.faculty_user = self._make_faculty("faculty1")

    def _make_faculty(self, username: str):
        user = User.objects.create_user(
            username=username,
            password="pass",
            email=f"{username}@am.amrita.edu",
        )
        profile = user.profile
        profile.role = Profile.ROLE_FACULTY
        profile.full_name = "Faculty User"
        profile.save(update_fields=["role", "full_name"])
        return user

    def test_signup_join_mode_stays_selected_on_validation_error(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "",
                "email": "student1@am.students.amrita.edu",
                "full_name": "Student One",
                "phone": "9999999999",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "group_mode": "join",
                # Intentionally missing join_group_code to trigger validation.
                "semester": "S6",
                "student_class": "CSE",
                "faculty_incharge": "",
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode("utf-8"),
            r'name="group_mode"[^>]*value="join"[^>]*checked',
        )

    def test_resend_signup_otp_requires_post(self):
        response = self.client.get(reverse("resend_signup_otp"), secure=True)
        self.assertEqual(response.status_code, 405)

    def test_resend_password_reset_otp_requires_post(self):
        response = self.client.get(reverse("resend_password_reset_otp"), secure=True)
        self.assertEqual(response.status_code, 405)

    def test_password_reset_request_does_not_enumerate_missing_account(self):
        response = self.client.post(
            reverse("password_reset"),
            {"email": "no-user@am.students.amrita.edu"},
            secure=True,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_reset_otp_confirm"))

    def test_signup_rejects_invalid_phone_format(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "",
                "email": "student2@am.students.amrita.edu",
                "full_name": "Student Two",
                "phone": "abc123",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "group_mode": "create",
                "group_name": "Team X",
                "semester": "S6",
                "student_class": "CSE",
                "faculty_incharge": str(self.faculty_user.profile.id),
            },
            secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid phone number")
