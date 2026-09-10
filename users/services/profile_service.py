import hashlib
import logging
import re
from random import randint
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q

from users.models import Profile

logger = logging.getLogger(__name__)

PROFILE_PHONE_REGEX = re.compile(r"^\d{10}$")
FULL_NAME_REGEX = re.compile(r"^[A-Za-z ]+$")


def client_ip(request) -> str:
    """Extract client IP address from HTTP request headers."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def is_rate_limited(request, scope: str, identity: str, limit: int, window_seconds: int) -> bool:
    """Check and increment rate limits in Django cache."""
    raw = f"{scope}:{client_ip(request)}:{(identity or '').strip().lower()}"
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


def faculty_user_for_value(raw_value: str) -> Optional[User]:
    """Find a Faculty User matching username, email, or full_name."""
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


def normalize_and_validate_phone(raw_phone: str) -> Optional[str]:
    """Validate 10-digit phone number format."""
    digits = re.sub(r"\D", "", raw_phone or "")
    if not digits or not PROFILE_PHONE_REGEX.match(digits):
        return None
    return digits


def validate_email_uniqueness(user: User, raw_email: str) -> tuple[Optional[str], Optional[str]]:
    """Ensure email is non-empty and unique across User accounts."""
    email = (raw_email or "").strip().lower()
    if not email:
        return None, "Email cannot be empty."
    if User.objects.filter(email__iexact=email).exclude(id=user.id).exists():
        return None, "This email is already used by another account."
    return email, None


def validate_username_uniqueness(user: User, raw_username: str) -> tuple[Optional[str], Optional[str]]:
    """Ensure username is non-empty and unique across User accounts."""
    username = (raw_username or "").strip()
    if not username:
        return None, "Username cannot be empty."
    if User.objects.filter(username__iexact=username).exclude(id=user.id).exists():
        return None, "This username is already used by another account."
    return username, None


def validate_full_name_format(raw_full_name: str) -> tuple[Optional[str], Optional[str]]:
    """Ensure full name contains only letters and spaces."""
    full_name = (raw_full_name or "").strip()
    if not full_name:
        return None, "Full name is required."
    if not FULL_NAME_REGEX.match(full_name):
        return None, "Full name must contain only alphabets and spaces."
    return " ".join(full_name.split()), None


def generate_otp_code() -> str:
    """Generate a random 6-digit numeric OTP code."""
    return f"{randint(0, 999999):06d}"


def send_otp_email(target_email: str, code: str, purpose_label: str) -> None:
    """Send an OTP email to the user via Django's configured email backend."""
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
