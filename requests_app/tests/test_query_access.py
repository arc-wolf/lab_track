from django.contrib.auth.models import User
from django.test import TestCase

from requests_app.models import BorrowRequest
from requests_app.services import get_requests_for_user
from users.models import Group, GroupMember, Profile


def make_user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password="pass", email=f"{username}@example.com")
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role"])
    return user


class QueryAccessTests(TestCase):
    def test_student_with_stale_group_id_cannot_read_group_requests_without_membership(self):
        faculty = make_user("faculty_q", Profile.ROLE_FACULTY)
        owner = make_user("owner_q", Profile.ROLE_STUDENT)
        outsider = make_user("outsider_q", Profile.ROLE_STUDENT)

        group = Group.objects.create(code="QSEC01", name="Secure Team", faculty=faculty)
        GroupMember.objects.create(group=group, user=owner, role=GroupMember.ROLE_LEADER)

        owner.profile.group_id = group.code
        owner.profile.save(update_fields=["group_id"])
        outsider.profile.group_id = group.code
        outsider.profile.save(update_fields=["group_id"])

        group_slip = BorrowRequest.objects.create(user=owner, faculty=faculty, group=group, project_title="Group request")
        own_slip = BorrowRequest.objects.create(user=outsider, faculty=faculty, project_title="Own request")

        visible = get_requests_for_user(outsider, BorrowRequest.objects.all())
        self.assertIn(own_slip, visible)
        self.assertNotIn(group_slip, visible)

