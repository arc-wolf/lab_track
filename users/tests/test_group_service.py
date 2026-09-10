from django.contrib.auth.models import User
from django.test import TestCase

from users.models import Group, GroupMember, GroupRemovalRequest, Profile
from users.services.group_service import (
    ensure_group_leader,
    process_cancel_removal,
    process_confirm_removal,
    process_start_removal,
    resolve_student_group,
)


class GroupServiceTests(TestCase):
    def setUp(self):
        self.faculty = User.objects.create_user("faculty_grp", password="Password123!")
        self.faculty.profile.role = Profile.ROLE_FACULTY
        self.faculty.profile.save()

        self.leader = User.objects.create_user("leader_user", password="Password123!")
        self.leader.profile.role = Profile.ROLE_STUDENT
        self.leader.profile.group_id = "GRP_TEST"
        self.leader.profile.save()

        self.member = User.objects.create_user("member_user", password="Password123!")
        self.member.profile.role = Profile.ROLE_STUDENT
        self.member.profile.group_id = "GRP_TEST"
        self.member.profile.save()

        self.group = Group.objects.create(
            code="GRP_TEST",
            name="Test Group",
            faculty=self.faculty,
            status=Group.STATUS_APPROVED,
        )
        self.member_leader = GroupMember.objects.create(
            group=self.group, user=self.leader, role=GroupMember.ROLE_LEADER
        )
        self.member_normal = GroupMember.objects.create(
            group=self.group, user=self.member, role=GroupMember.ROLE_MEMBER
        )

    def test_resolve_student_group(self):
        resolved = resolve_student_group(self.leader)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.code, "GRP_TEST")

    def test_ensure_group_leader(self):
        ensure_group_leader(self.group)
        self.assertTrue(self.group.members.filter(role=GroupMember.ROLE_LEADER).exists())

    def test_removal_workflow_leader_initiates(self):
        # Leader initiates removal of member
        ok, msg = process_start_removal(self.group, self.leader, is_leader=True, target_user_id=self.member.id)
        self.assertTrue(ok)

        removal_req = GroupRemovalRequest.objects.get(group=self.group, member=self.member)
        self.assertTrue(removal_req.leader_confirmed)
        self.assertFalse(removal_req.member_confirmed)

        # Member confirms removal
        ok, msg = process_confirm_removal(self.group, self.member, is_leader=False, request_id=removal_req.id)
        self.assertTrue(ok)
        self.assertFalse(GroupMember.objects.filter(group=self.group, user=self.member).exists())

    def test_removal_workflow_member_initiates_and_cancels(self):
        # Member initiates self removal
        ok, msg = process_start_removal(self.group, self.member, is_leader=False, target_user_id=self.member.id)
        self.assertTrue(ok)

        removal_req = GroupRemovalRequest.objects.get(group=self.group, member=self.member)
        self.assertTrue(removal_req.member_confirmed)

        # Leader cancels removal
        ok, msg = process_cancel_removal(self.group, self.leader, is_leader=True, request_id=removal_req.id)
        self.assertTrue(ok)
        removal_req.refresh_from_db()
        self.assertEqual(removal_req.status, GroupRemovalRequest.STATUS_CANCELLED)
        self.assertTrue(GroupMember.objects.filter(group=self.group, user=self.member).exists())
