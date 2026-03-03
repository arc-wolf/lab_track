from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
import secrets


def generate_api_token_key() -> str:
    return secrets.token_hex(32)


class Profile(models.Model):
    ROLE_STUDENT = "student"
    ROLE_FACULTY = "faculty"
    ROLE_ADMIN = "admin"

    ROLE_CHOICES = [
        (ROLE_STUDENT, "Student"),
        (ROLE_FACULTY, "Faculty"),
        (ROLE_ADMIN, "Lab Incharge"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STUDENT)
    semester = models.CharField(max_length=20, blank=True)
    student_class = models.CharField(max_length=50, blank=True)
    group_id = models.CharField(max_length=50, blank=True)
    group_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    faculty_incharge = models.CharField(max_length=100, blank=True)
    full_name = models.CharField(max_length=150, blank=True)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


class Group(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100, blank=True)
    faculty = models.ForeignKey(User, related_name="lab_groups", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class GroupMember(models.Model):
    ROLE_LEADER = "LEADER"
    ROLE_MEMBER = "MEMBER"
    ROLE_CHOICES = [
        (ROLE_LEADER, "Leader"),
        (ROLE_MEMBER, "Member"),
    ]

    group = models.ForeignKey(Group, related_name="members", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="group_memberships", on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="unique_group_user"),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.group.code}"


class GroupRemovalRequest(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    INITIATED_BY_MEMBER = "MEMBER"
    INITIATED_BY_LEADER = "LEADER"
    INITIATED_BY_CHOICES = [
        (INITIATED_BY_MEMBER, "Member"),
        (INITIATED_BY_LEADER, "Leader"),
    ]

    group = models.ForeignKey(Group, related_name="removal_requests", on_delete=models.CASCADE)
    member = models.ForeignKey(User, related_name="group_removal_requests", on_delete=models.CASCADE)
    initiated_by = models.CharField(max_length=10, choices=INITIATED_BY_CHOICES)
    member_confirmed = models.BooleanField(default=False)
    leader_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "member", "status"],
                condition=models.Q(status="PENDING"),
                name="unique_pending_group_removal_request",
            ),
        ]

    def __str__(self):
        return f"Removal {self.group.code}:{self.member.username} [{self.status}]"


class EmailOTP(models.Model):
    PURPOSE_SIGNUP = "SIGNUP"
    PURPOSE_PASSWORD_RESET = "PASSWORD_RESET"
    PURPOSE_CHOICES = [
        (PURPOSE_SIGNUP, "Signup"),
        (PURPOSE_PASSWORD_RESET, "Password Reset"),
    ]

    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} [{self.purpose}]"

    @classmethod
    def create_code(cls, email: str, purpose: str, code: str, ttl_minutes: int = 10):
        cls.objects.filter(email=email, purpose=purpose, is_used=False).update(is_used=True)
        return cls.objects.create(
            email=email,
            purpose=purpose,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )

    def matches(self, entered_code: str) -> bool:
        return (not self.is_used) and timezone.now() <= self.expires_at and self.code == (entered_code or "").strip()


class APIToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="api_token")
    key = models.CharField(max_length=64, unique=True, db_index=True, default=generate_api_token_key)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"API Token for {self.user.username}"

    def rotate(self):
        self.key = generate_api_token_key()
        self.save(update_fields=["key", "last_used_at"])

    def touch(self):
        self.save(update_fields=["last_used_at"])
