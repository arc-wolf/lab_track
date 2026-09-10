import json
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from inventory.models import Component
from requests_app.models import BorrowItem, BorrowRequest, LabPolicy
from users.models import APIToken, Group, GroupMember, Profile


def create_user_with_role(username: str, role: str, email: str = None) -> User:
    email = email or f"{username}@example.com"
    user = User.objects.create_user(username=username, password="Password123!", email=email)
    profile = user.profile
    profile.role = role
    profile.full_name = username.replace("_", " ").title()
    profile.phone = "9876543210"
    if role == Profile.ROLE_STUDENT:
        profile.semester = "S5"
        profile.student_class = "CSE-A"
        profile.group_id = "GRP101"
        profile.group_name = "Robotics Team"
        profile.faculty_incharge = "Dr. Faculty"
    profile.save()
    return user


class RoleBasedAttributesAndPermissionsTests(TestCase):
    def setUp(self):
        self.admin = create_user_with_role("sys_admin", Profile.ROLE_ADMIN)
        self.faculty_a = create_user_with_role("faculty_a", Profile.ROLE_FACULTY)
        self.faculty_b = create_user_with_role("faculty_b", Profile.ROLE_FACULTY)
        self.student_leader = create_user_with_role("student_leader", Profile.ROLE_STUDENT)
        self.student_member = create_user_with_role("student_member", Profile.ROLE_STUDENT)

        # Setup group
        self.group = Group.objects.create(
            code="GRP101",
            name="Robotics Team",
            faculty=self.faculty_a,
            status=Group.STATUS_APPROVED,
        )
        GroupMember.objects.create(group=self.group, user=self.student_leader, role=GroupMember.ROLE_LEADER)
        GroupMember.objects.create(group=self.group, user=self.student_member, role=GroupMember.ROLE_MEMBER)

        # Setup component
        self.component = Component.objects.create(
            name="Arduino Uno",
            category="Microcontrollers",
            total_stock=10,
            available_stock=8,
            student_limit=2,
            faculty_limit=5,
        )

        # Setup borrow request assigned to Faculty A
        self.borrow_req = BorrowRequest.objects.create(
            user=self.student_leader,
            faculty=self.faculty_a,
            group=self.group,
            project_title="Autonomous Rover",
            status=BorrowRequest.STATUS_PENDING,
        )
        BorrowItem.objects.create(borrow_request=self.borrow_req, component=self.component, quantity=2)

    # 1. Role Attribute Integrity Tests
    def test_role_attributes_correctness(self):
        # Student attributes
        student_prof = self.student_leader.profile
        self.assertEqual(student_prof.role, Profile.ROLE_STUDENT)
        self.assertEqual(student_prof.semester, "S5")
        self.assertEqual(student_prof.student_class, "CSE-A")
        self.assertEqual(student_prof.group_id, "GRP101")
        self.assertEqual(student_prof.group_name, "Robotics Team")
        self.assertEqual(student_prof.faculty_incharge, "Dr. Faculty")

        # Faculty attributes
        faculty_prof = self.faculty_a.profile
        self.assertEqual(faculty_prof.role, Profile.ROLE_FACULTY)
        self.assertEqual(faculty_prof.full_name, "Faculty A")

        # Admin attributes
        admin_prof = self.admin.profile
        self.assertEqual(admin_prof.role, Profile.ROLE_ADMIN)

    # 2. Dashboard Role Access Boundaries
    def test_dashboard_redirect_by_role(self):
        # Student redirect
        self.client.force_login(self.student_leader)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("student_dashboard"))

        # Faculty redirect
        self.client.force_login(self.faculty_a)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("faculty_dashboard"))

        # Admin redirect
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("admin_dashboard"))

    def test_student_blocked_from_faculty_and_admin_views(self):
        self.client.force_login(self.student_leader)

        # Faculty dashboard
        resp = self.client.get(reverse("faculty_dashboard"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Admin dashboard
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Admin inventory components console
        resp = self.client.get(reverse("admin_components"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Admin data console
        resp = self.client.get(reverse("admin_data_console"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

    def test_faculty_blocked_from_admin_views(self):
        self.client.force_login(self.faculty_a)

        # Admin dashboard
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Admin components console
        resp = self.client.get(reverse("admin_components"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Admin policy component console
        resp = self.client.get(reverse("admin_component_console"))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

    # 3. Request Approval & Action Role Restrictions
    def test_faculty_cannot_approve_unassigned_request(self):
        # Faculty B attempts to approve slip assigned to Faculty A
        self.client.force_login(self.faculty_b)
        resp = self.client.post(reverse("approve_slip", args=[self.borrow_req.id]))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
        self.borrow_req.refresh_from_db()
        self.assertEqual(self.borrow_req.status, BorrowRequest.STATUS_PENDING)

    def test_faculty_can_approve_assigned_request(self):
        # Faculty A approves slip assigned to Faculty A
        self.client.force_login(self.faculty_a)
        resp = self.client.post(reverse("approve_slip", args=[self.borrow_req.id]))
        self.assertRedirects(resp, reverse("faculty_dashboard"), fetch_redirect_response=False)
        self.borrow_req.refresh_from_db()
        self.assertEqual(self.borrow_req.status, BorrowRequest.STATUS_APPROVED)

    def test_student_cannot_perform_admin_slip_actions(self):
        self.client.force_login(self.student_leader)

        # Mark issued
        resp = self.client.post(
            reverse("mark_issued", args=[self.borrow_req.id]),
            {"collector_name": "Student Leader"},
        )
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Mark returned
        resp = self.client.post(
            reverse("mark_returned", args=[self.borrow_req.id]),
            {"condition": "Good"},
        )
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Mark penalty
        resp = self.client.post(
            reverse("mark_penalty", args=[self.borrow_req.id]),
            {"note": "Late return"},
        )
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

    def test_admin_can_perform_all_slip_actions(self):
        self.client.force_login(self.admin)

        # Approve
        self.client.post(reverse("approve_slip", args=[self.borrow_req.id]))
        self.borrow_req.refresh_from_db()
        self.assertEqual(self.borrow_req.status, BorrowRequest.STATUS_APPROVED)

        # Issue
        self.client.post(
            reverse("mark_issued", args=[self.borrow_req.id]),
            {"collector_name": "Student Leader"},
        )
        self.borrow_req.refresh_from_db()
        self.assertEqual(self.borrow_req.status, BorrowRequest.STATUS_ISSUED)

        # Return
        self.client.post(
            reverse("mark_returned", args=[self.borrow_req.id]),
            {"condition": "Ok"},
        )
        self.borrow_req.refresh_from_db()
        self.assertEqual(self.borrow_req.status, BorrowRequest.STATUS_RETURNED)

    # 4. Inventory CRUD Role Restrictions
    def test_non_admin_cannot_manage_inventory_components(self):
        self.client.force_login(self.student_leader)

        # Create
        resp = self.client.post(
            reverse("admin_component_create"),
            {"name": "Raspberry Pi 5", "category": "Boards", "total_stock": 5, "available_stock": 5},
        )
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
        self.assertFalse(Component.objects.filter(name="Raspberry Pi 5").exists())

        # Edit
        resp = self.client.post(
            reverse("admin_component_edit", args=[self.component.id]),
            {"name": "Arduino Uno Rev3", "category": "Boards", "total_stock": 10, "available_stock": 8},
        )
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)

        # Delete
        resp = self.client.post(reverse("admin_component_delete", args=[self.component.id]))
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(Component.objects.filter(id=self.component.id).exists())


    def test_admin_can_manage_inventory_components(self):
        self.client.force_login(self.admin)

        # Create
        resp = self.client.post(
            reverse("admin_component_create"),
            {"name": "Raspberry Pi 5", "category": "Boards", "total_stock": 5, "available_stock": 5, "student_limit": 1, "faculty_limit": 2},
        )
        self.assertRedirects(resp, reverse("admin_components"))
        self.assertTrue(Component.objects.filter(name="Raspberry Pi 5").exists())

    # 5. API Token Role Security
    def _issue_token(self, username: str) -> str:
        token, _ = APIToken.objects.get_or_create(user=User.objects.get(username=username))
        return token.key

    def test_api_admin_routes_enforce_admin_role(self):
        student_token = self._issue_token(self.student_leader.username)
        faculty_token = self._issue_token(self.faculty_a.username)
        admin_token = self._issue_token(self.admin.username)

        # Student token -> 403 on admin overview
        resp = self.client.get(
            reverse("api_admin_overview"),
            HTTP_AUTHORIZATION=f"Token {student_token}",
        )
        self.assertEqual(resp.status_code, 403)

        # Faculty token -> 403 on admin overview
        resp = self.client.get(
            reverse("api_admin_overview"),
            HTTP_AUTHORIZATION=f"Token {faculty_token}",
        )
        self.assertEqual(resp.status_code, 403)

        # Admin token -> 200 OK
        resp = self.client.get(
            reverse("api_admin_overview"),
            HTTP_AUTHORIZATION=f"Token {admin_token}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("overview", resp.json())
