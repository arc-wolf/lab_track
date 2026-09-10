from django.contrib.auth.models import User
from django.test import TestCase

from inventory.models import Component
from notifications.services.notification_service import (
    build_notifications_context,
    get_admin_notifications,
    get_faculty_notifications,
    get_student_notifications,
)
from requests_app.models import BorrowRequest
from users.models import Group, Profile


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin_notif", password="Password123!")
        self.admin.profile.role = Profile.ROLE_ADMIN
        self.admin.profile.save()

        self.faculty = User.objects.create_user("faculty_notif", password="Password123!", email="prof@example.com")
        self.faculty.profile.role = Profile.ROLE_FACULTY
        self.faculty.profile.full_name = "Prof Notif"
        self.faculty.profile.save()

        self.student = User.objects.create_user("student_notif", password="Password123!")
        self.student.profile.role = Profile.ROLE_STUDENT
        self.student.profile.save()

        self.component = Component.objects.create(
            name="Low Stock Sensor",
            category="Sensors",
            total_stock=5,
            available_stock=1,
        )

        self.group = Group.objects.create(
            code="GRP_NOTIF",
            name="Notif Group",
            faculty=self.faculty,
            status=Group.STATUS_PENDING,
        )

        self.borrow_req = BorrowRequest.objects.create(
            user=self.student,
            faculty=self.faculty,
            group=self.group,
            project_title="Sensor Test",
            status=BorrowRequest.STATUS_PENDING,
        )

    def test_admin_notifications(self):
        context = get_admin_notifications()
        self.assertIn("low_stock", context)
        self.assertIn("pending", context)
        self.assertIn("due_today", context)
        self.assertEqual(context["low_stock"].count(), 1)
        self.assertEqual(context["pending"].count(), 1)

    def test_faculty_notifications(self):
        context = get_faculty_notifications(self.faculty)
        self.assertIn("my_group_requests", context)
        self.assertIn("my_pending", context)
        self.assertEqual(context["my_group_requests"].count(), 1)
        self.assertEqual(context["my_pending"].count(), 1)

    def test_student_notifications(self):
        context = get_student_notifications(self.student)
        self.assertIn("my_requests", context)
        self.assertEqual(context["my_requests"].count(), 1)

    def test_build_notifications_context(self):
        admin_ctx = build_notifications_context(self.admin)
        self.assertEqual(admin_ctx["role"], Profile.ROLE_ADMIN)
        self.assertIn("low_stock", admin_ctx)

        faculty_ctx = build_notifications_context(self.faculty)
        self.assertEqual(faculty_ctx["role"], Profile.ROLE_FACULTY)
        self.assertIn("my_group_requests", faculty_ctx)

        student_ctx = build_notifications_context(self.student)
        self.assertEqual(student_ctx["role"], Profile.ROLE_STUDENT)
        self.assertIn("my_requests", student_ctx)
