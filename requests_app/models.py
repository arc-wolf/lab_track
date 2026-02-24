from django.db import models
from django.contrib.auth.models import User
from inventory.models import Component

from datetime import timedelta
from django.utils import timezone
from users.models import Group

class BorrowRequest(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_TERMINATED = "TERMINATED"
    STATUS_RETURNED = "RETURNED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_TERMINATED, "Terminated"),
        (STATUS_RETURNED, "Returned"),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="borrow_requests")
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name="borrow_requests")
    faculty = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="faculty_requests")
    counsellor = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    due_date = models.DateField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    return_condition = models.CharField(max_length=200, blank=True)
    return_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Request #{self.id} - {self.student.username}"

    def save(self, *args, **kwargs):
        if not self.due_date and self.created_at:
            self.due_date = (self.created_at + timedelta(days=45)).date()
        super().save(*args, **kwargs)


class BorrowRequestItem(models.Model):
    request = models.ForeignKey(BorrowRequest, on_delete=models.CASCADE, related_name="items")
    component = models.ForeignKey(Component, on_delete=models.CASCADE)
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.component.name} x {self.quantity}"
