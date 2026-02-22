from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


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
