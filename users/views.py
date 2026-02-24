from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from .forms import SignupForm
from .models import Group, GroupMember, Profile
from django.contrib.auth.models import User

@login_required
def dashboard_redirect(request):
    role = getattr(getattr(request.user, "profile", None), "role", None)
    if role == "student":
        return redirect("student_dashboard")
    if role == "faculty":
        return redirect("faculty_dashboard")
    if role == "admin":
        return redirect("admin_dashboard")
    return redirect("login")


def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # ensure group + membership exists for students
            profile = getattr(user, "profile", None)
            if profile and profile.group_id:
                faculty_user = None
                if profile.faculty_incharge:
                    faculty_user = User.objects.filter(username=profile.faculty_incharge).first()
                group, _ = Group.objects.get_or_create(
                    code=profile.group_id,
                    defaults={"faculty": faculty_user, "name": profile.group_name},
                )
                if faculty_user and group.faculty_id != faculty_user.id:
                    group.faculty = faculty_user
                    group.save(update_fields=["faculty"])
                if profile.group_name and group.name != profile.group_name:
                    group.name = profile.group_name
                    group.save(update_fields=["name"])
                GroupMember.objects.get_or_create(group=group, user=user, defaults={"role": GroupMember.ROLE_MEMBER})
            return redirect("dashboard")
    else:
        form = SignupForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def faculty_groups(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        return redirect("dashboard")
    groups = Group.objects.filter(faculty=request.user).order_by("-created_at")
    return render(request, "faculty/groups.html", {"groups": groups})


@login_required
def group_approve(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id, faculty=request.user)
    group.status = Group.STATUS_APPROVED
    group.save(update_fields=["status"])
    return redirect("faculty_groups")


@login_required
def group_reject(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id, faculty=request.user)
    group.status = Group.STATUS_REJECTED
    group.save(update_fields=["status"])
    return redirect("faculty_groups")


@login_required
def admin_groups(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        return redirect("dashboard")
    groups = Group.objects.all().order_by("-created_at")
    return render(request, "admin/groups.html", {"groups": groups})


@login_required
def admin_group_approve(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id)
    group.status = Group.STATUS_APPROVED
    group.save(update_fields=["status"])
    return redirect("admin_groups")


@login_required
def admin_group_reject(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id)
    group.status = Group.STATUS_REJECTED
    group.save(update_fields=["status"])
    return redirect("admin_groups")
