from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.http import require_POST
from random import randint
import logging
import hashlib
import re

from .forms import (
    FullNameAuthenticationForm,
    OTPVerificationForm,
    PasswordResetOTPConfirmForm,
    PasswordResetOTPRequestForm,
    PHONE_REGEX,
    SignupForm,
    normalize_phone,
)
from .models import EmailOTP, Group, GroupMember, GroupRemovalRequest, Profile
from requests_app.models import BorrowRequest

logger = logging.getLogger(__name__)
PROFILE_PHONE_REGEX = re.compile(r"^\d{10}$")
FULL_NAME_REGEX = re.compile(r"^[A-Za-z ]+$")


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limited(request, scope: str, identity: str, limit: int, window_seconds: int) -> bool:
    raw = f"{scope}:{_client_ip(request)}:{(identity or '').strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    key = f"rl:{digest}"
    if cache.add(key, 1, timeout=window_seconds):
        return False
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        count = 1
    return count > limit


def _faculty_user_for_value(raw_value: str):
    value = (raw_value or "").strip()
    if not value:
        return None
    return (
        User.objects.filter(profile__role=Profile.ROLE_FACULTY)
        .filter(
            Q(username=value)
            | Q(email__iexact=value)
            | Q(profile__full_name__iexact=value)
        )
        .first()
    )


def _attach_legacy_groups_to_faculty(faculty_user):
    Group.objects.filter(
        faculty__isnull=True,
        members__user__profile__faculty_incharge__in=[
            faculty_user.username,
            faculty_user.email,
            getattr(getattr(faculty_user, "profile", None), "full_name", ""),
        ],
    ).update(faculty=faculty_user)


def _validated_phone_or_message(request, raw_phone: str):
    phone = normalize_phone(raw_phone)
    if not phone or not PROFILE_PHONE_REGEX.match(phone):
        messages.error(request, "Enter a valid 10-digit mobile number.")
        return None
    return phone


def _validated_email_or_message(request, user, raw_email: str):
    email = (raw_email or "").strip().lower()
    if not email:
        messages.error(request, "Email cannot be empty.")
        return None
    if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
        messages.error(request, "This email is already used by another account.")
        return None
    return email


def _validated_username_or_message(request, user, raw_username: str):
    username = (raw_username or "").strip()
    if not username:
        messages.error(request, "Username cannot be empty.")
        return None
    if User.objects.filter(username__iexact=username).exclude(id=user.id).exists():
        messages.error(request, "This username is already used by another account.")
        return None
    return username


def _validated_full_name_or_message(request, raw_full_name: str):
    full_name = (raw_full_name or "").strip()
    if not full_name:
        messages.error(request, "Full name is required.")
        return None
    if not FULL_NAME_REGEX.match(full_name):
        messages.error(request, "Full name must contain only alphabets and spaces.")
        return None
    return " ".join(full_name.split())


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


class LabTrackLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = FullNameAuthenticationForm
    redirect_authenticated_user = True


def _generate_otp_code() -> str:
    return f"{randint(0, 999999):06d}"


def _send_otp_email(target_email: str, code: str, purpose_label: str):
    send_mail(
        f"LabTrack {purpose_label} OTP",
        (
            f"Your LabTrack OTP for {purpose_label.lower()} is: {code}\n\n"
            "This OTP is valid for 10 minutes.\n"
            "If you did not request this, please ignore this email."
        ),
        getattr(settings, "DEFAULT_FROM_EMAIL", "labtrack@localhost"),
        [target_email],
        fail_silently=False,
    )


def _serialize_signup_form(form: SignupForm):
    selected_faculty = form.cleaned_data.get("faculty_incharge")
    return {
        "username": form.cleaned_data.get("username", ""),
        "email": form.cleaned_data.get("email", ""),
        "password1": form.cleaned_data.get("password1", ""),
        "password2": form.cleaned_data.get("password2", ""),
        "full_name": form.cleaned_data.get("full_name", ""),
        "phone": form.cleaned_data.get("phone", ""),
        "semester": form.cleaned_data.get("semester", ""),
        "student_class": form.cleaned_data.get("student_class", ""),
        "group_mode": form.cleaned_data.get("group_mode", ""),
        "join_group_code": form.cleaned_data.get("join_group_code", ""),
        "group_name": form.cleaned_data.get("group_name", ""),
        "group_id": form.cleaned_data.get("group_id", ""),
        "faculty_incharge": str(selected_faculty.id) if selected_faculty else "",
    }


def _rebuild_signup_form(payload: dict) -> SignupForm:
    return SignupForm(payload)


def signup(request):
    otp_form = OTPVerificationForm()
    otp_stage = bool(request.session.get("pending_signup_data"))
    if request.method == "POST" and request.POST.get("otp_stage") == "1":
        pending_data = request.session.get("pending_signup_data")
        pending_email = request.session.get("pending_signup_email")
        if not pending_data or not pending_email:
            messages.error(request, "Signup session expired. Please submit registration again.")
            return redirect("signup")

        otp_form = OTPVerificationForm(request.POST)
        if otp_form.is_valid():
            verify_limit = int(getattr(settings, "SIGNUP_OTP_VERIFY_RATE_LIMIT", 10))
            verify_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))
            if _rate_limited(request, "signup_verify", pending_email, verify_limit, verify_window):
                messages.error(request, "Too many OTP attempts. Please wait a few minutes and try again.")
                form = SignupForm(initial=pending_data)
                return render(
                    request,
                    "registration/signup.html",
                    {"form": form, "otp_form": otp_form, "otp_stage": True, "pending_email": pending_email},
                )
            otp_value = otp_form.cleaned_data["otp"]
            otp_record = (
                EmailOTP.objects.filter(
                    email=pending_email,
                    purpose=EmailOTP.PURPOSE_SIGNUP,
                    is_used=False,
                )
                .order_by("-created_at")
                .first()
            )
            if not otp_record or not otp_record.matches(otp_value):
                messages.error(request, "Invalid or expired OTP. Please try again or resend OTP.")
                form = SignupForm(initial=pending_data)
                return render(
                    request,
                    "registration/signup.html",
                    {"form": form, "otp_form": otp_form, "otp_stage": True, "pending_email": pending_email},
                )

            form = _rebuild_signup_form(pending_data)
            if not form.is_valid():
                messages.error(request, "Registration details became invalid. Please submit the form again.")
                request.session.pop("pending_signup_data", None)
                request.session.pop("pending_signup_email", None)
                return redirect("signup")

            user = form.save()
            otp_record.is_used = True
            otp_record.save(update_fields=["is_used"])
            request.session.pop("pending_signup_data", None)
            request.session.pop("pending_signup_email", None)

            login(request, user)
            messages.success(request, "Account created successfully after OTP verification.")
            # ensure group + membership exists for students
            profile = getattr(user, "profile", None)
            mode = (form.cleaned_data.get("group_mode") or "").strip().lower()
            if profile and profile.group_id:
                faculty_user = _faculty_user_for_value(profile.faculty_incharge)
                group, created = Group.objects.get_or_create(
                    code=profile.group_id,
                    defaults={"faculty": faculty_user, "name": profile.group_name},
                )
                if created:
                    if faculty_user:
                        group.faculty = faculty_user
                    if profile.group_name:
                        group.name = profile.group_name
                    group.save()
                elif faculty_user and not group.faculty_id:
                    group.faculty = faculty_user
                    group.save(update_fields=["faculty"])
                default_role = GroupMember.ROLE_LEADER if mode == "create" else GroupMember.ROLE_MEMBER
                membership, _ = GroupMember.objects.get_or_create(
                    group=group,
                    user=user,
                    defaults={"role": default_role},
                )
                if mode == "create" and membership.role != GroupMember.ROLE_LEADER:
                    membership.role = GroupMember.ROLE_LEADER
                    membership.save(update_fields=["role"])
                if created:
                    messages.success(request, f"Group created. Share this Group ID with teammates: {group.code}")
                else:
                    messages.success(request, f"Joined group {group.code}.")
            if profile and profile.role in (Profile.ROLE_STUDENT, Profile.ROLE_FACULTY):
                profile.email_locked = True
                profile.save(update_fields=["email_locked"])
            return redirect("dashboard")
    elif request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            code = _generate_otp_code()
            pending_payload = _serialize_signup_form(form)
            EmailOTP.create_code(form.cleaned_data["email"], EmailOTP.PURPOSE_SIGNUP, code)
            try:
                _send_otp_email(form.cleaned_data["email"], code, "Registration")
            except Exception as exc:
                logger.exception("Signup OTP email send failed for %s", form.cleaned_data["email"])
                messages.error(
                    request,
                    f"Unable to send OTP email now. {exc}" if settings.DEBUG else "Unable to send OTP email now. Please try again later.",
                )
                return render(request, "registration/signup.html", {"form": form})

            request.session["pending_signup_data"] = pending_payload
            request.session["pending_signup_email"] = form.cleaned_data["email"]
            request.session.modified = True
            otp_stage = True
            otp_form = OTPVerificationForm()
            messages.info(request, "A 6-digit OTP has been sent to your email. Enter it to complete registration.")
            return render(
                request,
                "registration/signup.html",
                {"form": form, "otp_form": otp_form, "otp_stage": True, "pending_email": form.cleaned_data["email"]},
            )
        messages.error(request, "Signup failed. Please correct the highlighted fields and try again.")
    else:
        form = SignupForm()
    context = {"form": form, "otp_form": otp_form, "otp_stage": otp_stage, "pending_email": request.session.get("pending_signup_email")}
    return render(request, "registration/signup.html", context)


@require_POST
def resend_signup_otp(request):
    pending_data = request.session.get("pending_signup_data")
    pending_email = request.session.get("pending_signup_email")
    if not pending_data or not pending_email:
        messages.error(request, "No pending signup found. Please register again.")
        return redirect("signup")

    resend_limit = int(getattr(settings, "OTP_RESEND_RATE_LIMIT", 5))
    resend_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))
    if _rate_limited(request, "signup_resend", pending_email, resend_limit, resend_window):
        messages.error(request, "Too many OTP resend requests. Please wait a few minutes.")
        return redirect("signup")

    code = _generate_otp_code()
    EmailOTP.create_code(pending_email, EmailOTP.PURPOSE_SIGNUP, code)
    try:
        _send_otp_email(pending_email, code, "Registration")
    except Exception as exc:
        logger.exception("Signup OTP resend failed for %s", pending_email)
        messages.error(
            request,
            f"Unable to resend OTP now. {exc}" if settings.DEBUG else "Unable to resend OTP now. Please try again.",
        )
        return redirect("signup")
    messages.success(request, "A new OTP has been sent to your email.")
    return redirect("signup")


def password_reset_request_otp(request):
    if request.method == "POST":
        form = PasswordResetOTPRequestForm(request.POST)
        if form.is_valid():
            target_email = form.cleaned_data["email"].strip().lower()
            req_limit = int(getattr(settings, "PASSWORD_RESET_REQUEST_RATE_LIMIT", 5))
            req_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))
            if _rate_limited(request, "pwd_reset_request", target_email, req_limit, req_window):
                messages.error(request, "Too many reset requests. Please wait a few minutes.")
                return render(request, "registration/password_reset_otp_request.html", {"form": form})

            user = User.objects.filter(email__iexact=target_email).first()
            request.session["password_reset_email"] = target_email
            request.session.modified = True
            if user:
                code = _generate_otp_code()
                EmailOTP.create_code(target_email, EmailOTP.PURPOSE_PASSWORD_RESET, code)
                try:
                    _send_otp_email(target_email, code, "Password Reset")
                except Exception as exc:
                    logger.exception("Password reset OTP send failed for %s", target_email)
                    messages.error(
                        request,
                        f"Unable to send reset OTP now. {exc}" if settings.DEBUG else "Unable to send reset OTP now. Please try again later.",
                    )
                    return render(request, "registration/password_reset_otp_request.html", {"form": form})
            # Generic response to avoid account enumeration.
            messages.info(request, "If an account exists for this email, a reset OTP has been sent.")
            return redirect("password_reset_otp_confirm")
    else:
        form = PasswordResetOTPRequestForm()
    return render(request, "registration/password_reset_otp_request.html", {"form": form})


def password_reset_confirm_otp(request):
    reset_email = request.session.get("password_reset_email")
    if not reset_email:
        messages.error(request, "Reset session expired. Start password reset again.")
        return redirect("password_reset")

    if request.method == "POST":
        form = PasswordResetOTPConfirmForm(request.POST)
        if form.is_valid():
            verify_limit = int(getattr(settings, "PASSWORD_RESET_OTP_VERIFY_RATE_LIMIT", 10))
            verify_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))
            if _rate_limited(request, "pwd_reset_verify", reset_email, verify_limit, verify_window):
                messages.error(request, "Too many OTP attempts. Please wait a few minutes and try again.")
                return render(
                    request,
                    "registration/password_reset_otp_confirm.html",
                    {"form": form, "reset_email": reset_email},
                )
            otp_record = (
                EmailOTP.objects.filter(
                    email=reset_email,
                    purpose=EmailOTP.PURPOSE_PASSWORD_RESET,
                    is_used=False,
                )
                .order_by("-created_at")
                .first()
            )
            if not otp_record or not otp_record.matches(form.cleaned_data["otp"]):
                messages.error(request, "Invalid or expired OTP.")
                return render(
                    request,
                    "registration/password_reset_otp_confirm.html",
                    {"form": form, "reset_email": reset_email},
                )

            user = User.objects.filter(email__iexact=reset_email).first()
            if not user:
                messages.error(request, "Invalid or expired OTP.")
                return render(
                    request,
                    "registration/password_reset_otp_confirm.html",
                    {"form": form, "reset_email": reset_email},
                )

            user.set_password(form.cleaned_data["new_password1"])
            user.save(update_fields=["password"])
            otp_record.is_used = True
            otp_record.save(update_fields=["is_used"])
            request.session.pop("password_reset_email", None)
            messages.success(request, "Password updated successfully. Please login.")
            return redirect("login")
    else:
        form = PasswordResetOTPConfirmForm()

    return render(
        request,
        "registration/password_reset_otp_confirm.html",
        {"form": form, "reset_email": reset_email},
    )


@require_POST
def resend_password_reset_otp(request):
    reset_email = request.session.get("password_reset_email")
    if not reset_email:
        messages.error(request, "Reset session expired. Start again.")
        return redirect("password_reset")

    user = User.objects.filter(email__iexact=reset_email).first()
    if not user:
        messages.info(request, "If an account exists for this email, a reset OTP has been sent.")
        return redirect("password_reset_otp_confirm")

    resend_limit = int(getattr(settings, "OTP_RESEND_RATE_LIMIT", 5))
    resend_window = int(getattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 600))
    if _rate_limited(request, "pwd_reset_resend", reset_email, resend_limit, resend_window):
        messages.error(request, "Too many OTP resend requests. Please wait a few minutes.")
        return redirect("password_reset_otp_confirm")

    code = _generate_otp_code()
    EmailOTP.create_code(reset_email, EmailOTP.PURPOSE_PASSWORD_RESET, code)
    try:
        _send_otp_email(reset_email, code, "Password Reset")
    except Exception as exc:
        logger.exception("Password reset OTP resend failed for %s", reset_email)
        messages.error(
            request,
            f"Unable to resend OTP now. {exc}" if settings.DEBUG else "Unable to resend OTP now. Please try again.",
        )
        return redirect("password_reset_otp_confirm")
    messages.success(request, "A new reset OTP has been sent.")
    return redirect("password_reset_otp_confirm")


@login_required
def faculty_groups(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        messages.error(request, "Only faculty can access group approval requests.")
        return redirect("dashboard")
    _attach_legacy_groups_to_faculty(request.user)
    groups = Group.objects.filter(faculty=request.user).order_by("-created_at")
    return render(request, "faculty/groups.html", {"groups": groups})


@login_required
@require_POST
def group_approve(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        messages.error(request, "You are not authorized to approve this group.")
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id, faculty=request.user)
    group.status = Group.STATUS_APPROVED
    group.save(update_fields=["status"])
    return redirect("faculty_groups")


@login_required
@require_POST
def group_reject(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        messages.error(request, "You are not authorized to reject this group.")
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id, faculty=request.user)
    group.status = Group.STATUS_REJECTED
    group.save(update_fields=["status"])
    return redirect("faculty_groups")


@login_required
def admin_groups(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        messages.error(request, "Only lab admin can access all groups.")
        return redirect("dashboard")
    groups = Group.objects.all().order_by("-created_at")
    return render(request, "admin/groups.html", {"groups": groups})


@login_required
def admin_student_console(request):
    """Hub for student-related admin work: group console + permission console."""
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        return redirect("dashboard")

    group_counts = Group.objects.aggregate(
        pending=Count("id", filter=Q(status=Group.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=Group.STATUS_APPROVED)),
        rejected=Count("id", filter=Q(status=Group.STATUS_REJECTED)),
    )

    permission_counts = BorrowRequest.objects.aggregate(
        pending=Count("id", filter=Q(status=BorrowRequest.STATUS_PENDING)),
        approved=Count("id", filter=Q(status=BorrowRequest.STATUS_APPROVED)),
        returned=Count("id", filter=Q(status=BorrowRequest.STATUS_RETURNED)),
    )

    context = {
        "group_counts": group_counts,
        "permission_counts": permission_counts,
    }
    return render(request, "admin/student_console.html", context)


@login_required
def admin_profile_console(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        return redirect("dashboard")

    if request.method == "POST":
        action = (request.POST.get("action") or "save_profile").strip()
        if action == "verify_email_otp":
            pending_email = request.session.get("pending_admin_email")
            otp_value = (request.POST.get("otp") or "").strip()
            if not pending_email:
                messages.error(request, "No pending email verification found.")
                return redirect("admin_profile_console")
            otp_record = (
                EmailOTP.objects.filter(
                    email=pending_email,
                    purpose=EmailOTP.PURPOSE_ADMIN_EMAIL_CHANGE,
                    is_used=False,
                )
                .order_by("-created_at")
                .first()
            )
            if not otp_record or not otp_record.matches(otp_value):
                messages.error(request, "Invalid or expired OTP.")
                return redirect("admin_profile_console")
            request.user.email = pending_email
            request.user.save(update_fields=["email"])
            profile.email_locked = True
            profile.save(update_fields=["email_locked"])
            otp_record.is_used = True
            otp_record.save(update_fields=["is_used"])
            request.session.pop("pending_admin_email", None)
            messages.success(request, "Email verified and locked successfully.")
            return redirect("admin_profile_console")

        full_name = _validated_full_name_or_message(request, request.POST.get("full_name", ""))
        if full_name is None:
            return redirect("admin_profile_console")
        username = _validated_username_or_message(request, request.user, request.POST.get("username", ""))
        if username is None:
            return redirect("admin_profile_console")
        phone = _validated_phone_or_message(request, request.POST.get("phone", ""))
        if phone is None:
            return redirect("admin_profile_console")
        requested_email = _validated_email_or_message(request, request.user, request.POST.get("email", ""))
        if requested_email is None:
            return redirect("admin_profile_console")
        password = request.POST.get("password", "").strip()

        request.user.username = username
        request.user.save(update_fields=["username"])
        profile.full_name = full_name
        profile.phone = phone
        profile.save(update_fields=["full_name", "phone"])

        current_email = (request.user.email or "").strip().lower()
        if requested_email != current_email:
            if profile.email_locked:
                messages.error(request, "Email is already verified and locked for this admin account.")
                return redirect("admin_profile_console")
            otp_record = EmailOTP.create_code(
                requested_email,
                EmailOTP.PURPOSE_ADMIN_EMAIL_CHANGE,
                _generate_otp_code(),
            )
            try:
                _send_otp_email(requested_email, otp_record.code, "Admin Email Change")
            except Exception as exc:
                logger.exception("Admin email OTP send failed for %s", requested_email)
                messages.error(
                    request,
                    f"Unable to send email verification OTP now. {exc}" if settings.DEBUG else "Unable to send email verification OTP now.",
                )
                return redirect("admin_profile_console")
            request.session["pending_admin_email"] = requested_email
            request.session.modified = True
            messages.info(request, "OTP sent to the new email. Verify to finalize and lock email.")
            return redirect("admin_profile_console")

        if password:
            request.user.set_password(password)
            request.user.save(update_fields=["password"])
            messages.success(request, "Profile updated. Please login again with your new password.")
            return redirect("login")

        messages.success(request, "Admin profile updated.")
        return redirect("admin_profile_console")

    return render(
        request,
        "admin/profile_console.html",
        {"admin_profile": profile, "pending_admin_email": request.session.get("pending_admin_email")},
    )


@login_required
def student_profile_console(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_STUDENT:
        return redirect("dashboard")

    if request.method == "POST":
        full_name = _validated_full_name_or_message(request, request.POST.get("full_name", ""))
        if full_name is None:
            return redirect("student_profile_console")
        username = _validated_username_or_message(request, request.user, request.POST.get("username", ""))
        if username is None:
            return redirect("student_profile_console")
        phone = _validated_phone_or_message(request, request.POST.get("phone", ""))
        if phone is None:
            return redirect("student_profile_console")
        semester = request.POST.get("semester", "").strip()
        student_class = request.POST.get("student_class", "").strip()
        password = request.POST.get("password", "").strip()

        request.user.username = username
        request.user.save(update_fields=["username"])
        profile.full_name = full_name
        profile.phone = phone
        profile.semester = semester
        profile.student_class = student_class
        profile.email_locked = True
        profile.save(update_fields=["full_name", "phone", "semester", "student_class", "email_locked"])
        messages.info(request, "Email is immutable for student accounts after verification.")
        if password:
            request.user.set_password(password)
            request.user.save(update_fields=["password"])
            messages.success(request, "Profile updated. Please login again with your new password.")
            return redirect("login")

        messages.success(request, "Student profile updated.")
        return redirect("student_profile_console")

    return render(
        request,
        "student/profile_console.html",
        {"student_profile": profile},
    )


def _resolve_student_group(user):
    profile = getattr(user, "profile", None)
    if not profile or profile.role != Profile.ROLE_STUDENT or not profile.group_id:
        return None
    group = Group.objects.filter(code__iexact=profile.group_id).first()
    if group and profile.group_id != group.code:
        profile.group_id = group.code
        profile.save(update_fields=["group_id"])
    return group


def _ensure_group_leader(group):
    if not group:
        return
    if group.members.filter(role=GroupMember.ROLE_LEADER).exists():
        return
    first_member = group.members.order_by("joined_at").first()
    if first_member:
        first_member.role = GroupMember.ROLE_LEADER
        first_member.save(update_fields=["role"])


@login_required
def student_group_console(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_STUDENT:
        return redirect("dashboard")

    group = _resolve_student_group(request.user)
    if not group:
        messages.error(request, "No group linked to your profile yet.")
        return redirect("student_dashboard")

    GroupMember.objects.get_or_create(
        group=group,
        user=request.user,
        defaults={"role": GroupMember.ROLE_MEMBER},
    )
    _ensure_group_leader(group)

    current_member = GroupMember.objects.get(group=group, user=request.user)
    is_leader = current_member.role == GroupMember.ROLE_LEADER

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        if action == "start_removal":
            target_user_id = request.POST.get("member_id")
            target_member = get_object_or_404(GroupMember, group=group, user_id=target_user_id)
            if target_member.role == GroupMember.ROLE_LEADER:
                messages.error(request, "Team leader cannot be removed from this screen.")
                return redirect("student_group_console")

            if is_leader and target_member.user_id != request.user.id:
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
                messages.info(request, f"Removal request started for {target_member.user.username}. Waiting member confirmation.")
            elif target_member.user_id == request.user.id:
                req, _ = GroupRemovalRequest.objects.get_or_create(
                    group=group,
                    member=request.user,
                    status=GroupRemovalRequest.STATUS_PENDING,
                    defaults={
                        "initiated_by": GroupRemovalRequest.INITIATED_BY_MEMBER,
                        "member_confirmed": True,
                    },
                )
                if not req.member_confirmed:
                    req.member_confirmed = True
                    req.save(update_fields=["member_confirmed"])
                messages.info(request, "Your self-removal request is created. Waiting team leader confirmation.")
            else:
                messages.error(request, "You are not authorized for this action.")

        elif action == "confirm_removal":
            req_id = request.POST.get("request_id")
            removal_req = get_object_or_404(
                GroupRemovalRequest,
                id=req_id,
                group=group,
                status=GroupRemovalRequest.STATUS_PENDING,
            )

            changed = False
            if removal_req.member_id == request.user.id and not removal_req.member_confirmed:
                removal_req.member_confirmed = True
                changed = True
            if is_leader and not removal_req.leader_confirmed:
                removal_req.leader_confirmed = True
                changed = True
            if not changed:
                messages.error(request, "No valid confirmation action available.")
                return redirect("student_group_console")

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
                messages.success(request, f"{removal_req.member.username} has been removed from the team.")
            else:
                removal_req.save(update_fields=["member_confirmed", "leader_confirmed"])
                messages.info(request, "Confirmation recorded. Waiting for the other party.")

        elif action == "cancel_removal":
            req_id = request.POST.get("request_id")
            removal_req = get_object_or_404(
                GroupRemovalRequest,
                id=req_id,
                group=group,
                status=GroupRemovalRequest.STATUS_PENDING,
            )
            if removal_req.member_id == request.user.id or is_leader:
                removal_req.status = GroupRemovalRequest.STATUS_CANCELLED
                removal_req.processed_at = timezone.now()
                removal_req.save(update_fields=["status", "processed_at"])
                messages.warning(request, "Removal request cancelled.")
            else:
                messages.error(request, "Not authorized to cancel this request.")

        return redirect("student_group_console")

    members = group.members.select_related("user").order_by("-role", "joined_at")
    pending_removals = group.removal_requests.filter(status=GroupRemovalRequest.STATUS_PENDING).select_related("member")
    context = {
        "group": group,
        "members": members,
        "current_member": current_member,
        "is_leader": is_leader,
        "pending_removals": pending_removals,
    }
    return render(request, "student/group_console.html", context)


@login_required
def faculty_profile_console(request):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_FACULTY:
        return redirect("dashboard")

    if request.method == "POST":
        full_name = _validated_full_name_or_message(request, request.POST.get("full_name", ""))
        if full_name is None:
            return redirect("faculty_profile_console")
        username = _validated_username_or_message(request, request.user, request.POST.get("username", ""))
        if username is None:
            return redirect("faculty_profile_console")
        phone = _validated_phone_or_message(request, request.POST.get("phone", ""))
        if phone is None:
            return redirect("faculty_profile_console")
        password = request.POST.get("password", "").strip()

        request.user.username = username
        request.user.save(update_fields=["username"])
        profile.full_name = full_name
        profile.phone = phone
        profile.email_locked = True
        profile.save(update_fields=["full_name", "phone", "email_locked"])
        messages.info(request, "Email is immutable for faculty accounts after verification.")
        if password:
            request.user.set_password(password)
            request.user.save(update_fields=["password"])
            messages.success(request, "Profile updated. Please login again with your new password.")
            return redirect("login")

        messages.success(request, "Faculty profile updated.")
        return redirect("faculty_profile_console")

    return render(
        request,
        "faculty/profile_console.html",
        {"faculty_profile": profile},
    )


@login_required
@require_POST
def admin_group_approve(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        messages.error(request, "Only lab admin can approve groups from this console.")
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id)
    group.status = Group.STATUS_APPROVED
    group.save(update_fields=["status"])
    return redirect("admin_groups")


@login_required
@require_POST
def admin_group_reject(request, group_id):
    profile = getattr(request.user, "profile", None)
    if not profile or profile.role != Profile.ROLE_ADMIN:
        messages.error(request, "Only lab admin can reject groups from this console.")
        return redirect("dashboard")
    group = get_object_or_404(Group, id=group_id)
    group.status = Group.STATUS_REJECTED
    group.save(update_fields=["status"])
    return redirect("admin_groups")
