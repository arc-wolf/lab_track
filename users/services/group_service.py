from typing import Optional, Tuple
from django.contrib.auth.models import User
from django.utils import timezone

from users.models import Group, GroupMember, GroupRemovalRequest, Profile


def resolve_student_group(user: User) -> Optional[Group]:
    """Resolve and sync student profile group code with Group record."""
    profile = getattr(user, "profile", None)
    if not profile or profile.role != Profile.ROLE_STUDENT or not profile.group_id:
        return None
    group = Group.objects.filter(code__iexact=profile.group_id).first()
    if group and profile.group_id != group.code:
        profile.group_id = group.code
        profile.save(update_fields=["group_id"])
    return group


def ensure_group_leader(group: Optional[Group]) -> None:
    """Ensure at least one member in the group is designated as leader."""
    if not group:
        return
    if group.members.filter(role=GroupMember.ROLE_LEADER).exists():
        return
    first_member = group.members.order_by("joined_at").first()
    if first_member:
        first_member.role = GroupMember.ROLE_LEADER
        first_member.save(update_fields=["role"])


def process_start_removal(
    group: Group,
    current_user: User,
    is_leader: bool,
    target_user_id: int | str,
) -> Tuple[bool, str]:
    """Initiate a group member removal request."""
    try:
        target_member = group.members.get(user_id=target_user_id)
    except GroupMember.DoesNotExist:
        return False, "Target group member not found."

    if target_member.role == GroupMember.ROLE_LEADER:
        return False, "Team leader cannot be removed from this screen."

    if is_leader and target_member.user_id != current_user.id:
        req, _ = GroupRemovalRequest.objects.get_or_create(
            group=group,
            member=target_member.user,
            status=GroupRemovalRequest.STATUS_PENDING,
            defaults={
                "initiated_by": GroupRemovalRequest.INITIATED_BY_LEADER,
                "leader_confirmed": True,
            },
        )
        if not req.leader_confirmed:
            req.leader_confirmed = True
            req.save(update_fields=["leader_confirmed"])
        return True, f"Removal request started for {target_member.user.username}. Waiting member confirmation."

    elif target_member.user_id == current_user.id:
        req, _ = GroupRemovalRequest.objects.get_or_create(
            group=group,
            member=current_user,
            status=GroupRemovalRequest.STATUS_PENDING,
            defaults={
                "initiated_by": GroupRemovalRequest.INITIATED_BY_MEMBER,
                "member_confirmed": True,
            },
        )
        if not req.member_confirmed:
            req.member_confirmed = True
            req.save(update_fields=["member_confirmed"])
        return True, "Your self-removal request is created. Waiting team leader confirmation."

    return False, "You are not authorized for this action."


def process_confirm_removal(
    group: Group,
    current_user: User,
    is_leader: bool,
    request_id: int | str,
) -> Tuple[bool, str]:
    """Confirm a pending removal request with dual consent checks."""
    try:
        removal_req = GroupRemovalRequest.objects.get(
            id=request_id,
            group=group,
            status=GroupRemovalRequest.STATUS_PENDING,
        )
    except GroupRemovalRequest.DoesNotExist:
        return False, "Pending removal request not found."

    changed = False
    if removal_req.member_id == current_user.id and not removal_req.member_confirmed:
        removal_req.member_confirmed = True
        changed = True
    if is_leader and not removal_req.leader_confirmed:
        removal_req.leader_confirmed = True
        changed = True

    if not changed:
        return False, "No valid confirmation action available."

    if removal_req.member_confirmed and removal_req.leader_confirmed:
        GroupMember.objects.filter(group=group, user=removal_req.member).delete()
        member_profile = getattr(removal_req.member, "profile", None)
        if member_profile and member_profile.group_id.upper() == group.code.upper():
            member_profile.group_id = ""
            member_profile.group_name = ""
            member_profile.faculty_incharge = ""
            member_profile.save(update_fields=["group_id", "group_name", "faculty_incharge"])
        removal_req.status = GroupRemovalRequest.STATUS_APPROVED
        removal_req.processed_at = timezone.now()
        removal_req.save(update_fields=["member_confirmed", "leader_confirmed", "status", "processed_at"])
        return True, f"{removal_req.member.username} has been removed from the team."

    removal_req.save(update_fields=["member_confirmed", "leader_confirmed"])
    return True, "Confirmation recorded. Waiting for the other party."


def process_cancel_removal(
    group: Group,
    current_user: User,
    is_leader: bool,
    request_id: int | str,
) -> Tuple[bool, str]:
    """Cancel a pending removal request."""
    try:
        removal_req = GroupRemovalRequest.objects.get(
            id=request_id,
            group=group,
            status=GroupRemovalRequest.STATUS_PENDING,
        )
    except GroupRemovalRequest.DoesNotExist:
        return False, "Pending removal request not found."

    if not (is_leader or removal_req.member_id == current_user.id):
        return False, "Not authorized to cancel this removal request."

    removal_req.status = GroupRemovalRequest.STATUS_CANCELLED
    removal_req.processed_at = timezone.now()
    removal_req.save(update_fields=["status", "processed_at"])
    return True, "Removal request cancelled."
