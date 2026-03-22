from requests_app.models import BorrowRequest
from users.models import Group, Profile


def get_requests_for_user(user, queryset=None):
    queryset = queryset or BorrowRequest.objects.all()
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", "")

    if role == Profile.ROLE_ADMIN:
        return queryset
    if role == Profile.ROLE_FACULTY:
        return queryset.filter(faculty=user)

    group_code = (getattr(profile, "group_id", "") or "").strip()
    if group_code:
        group = Group.objects.filter(code__iexact=group_code).first()
        if group:
            return queryset.filter(group=group)
    return queryset.filter(user=user)
