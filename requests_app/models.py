from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils import timezone
from inventory.models import Component
from users.models import Group


class BorrowRequest(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_TERMINATED = STATUS_REJECTED
    STATUS_ISSUED = "ISSUED"
    STATUS_RETURNED = "RETURNED"
    STATUS_PENALTY = "PENALTY"
    STATUS_OVERDUE = "OVERDUE"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_ISSUED, "Issued"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_PENALTY, "Penalty"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="borrow_requests",
        null=False,
        blank=False,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    faculty = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="faculty_requests",
        null=True,
        blank=True,
        limit_choices_to={"profile__role": "faculty"},
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="borrow_requests",
    )
    counsellor_name = models.CharField(max_length=200, default="")
    project_title = models.CharField(max_length=255, blank=True)
    cart_locked_at = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    return_condition = models.CharField(max_length=200, blank=True)
    return_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["faculty", "status", "created_at"], name="brreq_fac_stat_created_idx"),
            models.Index(fields=["group", "status", "created_at"], name="brreq_grp_stat_created_idx"),
            models.Index(fields=["status", "due_date"], name="borrowreq_status_due_idx"),
            models.Index(fields=["status", "reminder_sent", "due_date"], name="borrowreq_status_rem_due_idx"),
        ]

    def __init__(self, *args, **kwargs):
        # Backward-compat kwargs still used across views/tests/templates.
        student = kwargs.pop("student", None)
        counsellor = kwargs.pop("counsellor", None)
        super().__init__(*args, **kwargs)
        if student is not None:
            self.user = student
        if counsellor is not None:
            self.counsellor_name = counsellor

    def __str__(self):
        return f"BorrowRequest #{self.id} ({self.status})"

    @property
    def student(self):
        return self.user

    @student.setter
    def student(self, value):
        self.user = value

    @property
    def counsellor(self):
        return self.counsellor_name

    @counsellor.setter
    def counsellor(self, value):
        self.counsellor_name = value or ""

    def set_default_due(self):
        if not self.due_date:
            self.due_date = (timezone.now() + timedelta(days=45)).date()

    def save(self, *args, **kwargs):
        self.set_default_due()
        super().save(*args, **kwargs)

    # --- Status transitions with audit logging ---
    def approve(self, by_user):
        if self.status != self.STATUS_PENDING:
            raise ValueError("Invalid status transition")
        with transaction.atomic():
            self.status = self.STATUS_APPROVED
            self.save(update_fields=["status"])
            BorrowAction.objects.create(
                borrow_request=self,
                action=BorrowAction.ACTION_APPROVED,
                performed_by=by_user,
            )

    def reject(self, by_user, note=""):
        if self.status not in (self.STATUS_PENDING, self.STATUS_APPROVED):
            raise ValueError("Invalid status transition")
        with transaction.atomic():
            self.status = self.STATUS_REJECTED
            self.save(update_fields=["status"])
            BorrowAction.objects.create(
                borrow_request=self,
                action=BorrowAction.ACTION_REJECTED,
                performed_by=by_user,
                note=note,
            )

    def mark_issued(self, by_user, note=""):
        if self.status != self.STATUS_APPROVED:
            raise ValueError("Invalid status transition")
        with transaction.atomic():
            self.status = self.STATUS_ISSUED
            self.save(update_fields=["status"])
            BorrowAction.objects.create(
                borrow_request=self,
                action=BorrowAction.ACTION_ISSUED,
                performed_by=by_user,
                note=note,
            )

    def mark_returned(self, by_user, condition: str = None):
        if self.status not in (self.STATUS_APPROVED, self.STATUS_ISSUED, self.STATUS_OVERDUE, self.STATUS_PENALTY):
            raise ValueError("Invalid status transition")
        with transaction.atomic():
            self.status = self.STATUS_RETURNED
            self.return_condition = condition or ""
            self.return_time = timezone.now()
            self.save(update_fields=["status", "return_condition", "return_time"])
            BorrowAction.objects.create(
                borrow_request=self,
                action=BorrowAction.ACTION_RETURNED,
                performed_by=by_user,
                note=condition or "",
            )

    def mark_penalty(self, by_user, note=""):
        if self.status not in (self.STATUS_ISSUED, self.STATUS_OVERDUE):
            raise ValueError("Invalid status transition")
        with transaction.atomic():
            self.status = self.STATUS_PENALTY
            self.save(update_fields=["status"])
            BorrowAction.objects.create(
                borrow_request=self,
                action=BorrowAction.ACTION_PENALTY,
                performed_by=by_user,
                note=note,
            )

    def auto_mark_overdue(self):
        if self.status in (self.STATUS_APPROVED, self.STATUS_ISSUED) and self.due_date and timezone.now().date() > self.due_date:
            with transaction.atomic():
                self.status = self.STATUS_OVERDUE
                self.save(update_fields=["status"])
                BorrowAction.objects.create(
                    borrow_request=self,
                    action=BorrowAction.ACTION_AUTO_OVERDUE,
                    performed_by=self.user,  # fallback; system user could be used instead
                )


class BorrowItem(models.Model):
    borrow_request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="items")
    component = models.ForeignKey(Component, on_delete=models.PROTECT, related_name="borrow_items", db_index=True)
    quantity = models.PositiveIntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["borrow_request", "component"], name="borrowitem_req_comp_idx"),
        ]

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if request is not None:
            self.borrow_request = request

    def __str__(self):
        return f"{self.component.name} x {self.quantity}"

    @property
    def request(self):
        return self.borrow_request

    @request.setter
    def request(self, value):
        self.borrow_request = value


class BorrowAction(models.Model):
    ACTION_CREATED = "CREATED"
    ACTION_APPROVED = "APPROVED"
    ACTION_REJECTED = "REJECTED"
    ACTION_ISSUED = "ISSUED"
    ACTION_RETURNED = "RETURNED"
    ACTION_PENALTY = "PENALTY"
    ACTION_AUTO_OVERDUE = "AUTO_OVERDUE"

    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_APPROVED, "Approved"),
        (ACTION_REJECTED, "Rejected"),
        (ACTION_ISSUED, "Issued"),
        (ACTION_RETURNED, "Returned"),
        (ACTION_PENALTY, "Penalty"),
        (ACTION_AUTO_OVERDUE, "Auto Overdue"),
    ]

    borrow_request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="actions")
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    timestamp = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["borrow_request", "timestamp"], name="borrowaction_req_ts_idx"),
            models.Index(fields=["action", "timestamp"], name="borrowaction_action_ts_idx"),
        ]


class LabPolicy(models.Model):
    """
    Singleton-style admin policy for penalties and maintenance triggers.
    """

    per_day_fine = models.PositiveIntegerField(default=10)
    grace_days = models.PositiveIntegerField(default=2)
    overdue_penalty_trigger_days = models.PositiveIntegerField(default=5)
    damaged_fine = models.PositiveIntegerField(default=500)
    missing_parts_fine = models.PositiveIntegerField(default=700)
    not_working_fine = models.PositiveIntegerField(default=1000)
    maintenance_keywords = models.CharField(
        max_length=255,
        default="service,damaged,not working,missing",
    )
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Lab Policy"


# Backward-compat alias used by existing tests/admin code.
BorrowRequestItem = BorrowItem
