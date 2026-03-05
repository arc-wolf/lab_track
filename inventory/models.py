from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils import timezone


class Component(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, default="")
    total_stock = models.PositiveIntegerField(default=0)
    available_stock = models.PositiveIntegerField(default=0)
    student_limit = models.PositiveIntegerField(default=0)  # 0 = no limit
    faculty_limit = models.PositiveIntegerField(default=0)  # reserved for future faculty requests
    # Optional per-component fine overrides. Null => fallback to global LabPolicy.
    fine_per_day = models.PositiveIntegerField(null=True, blank=True)
    fine_damaged = models.PositiveIntegerField(null=True, blank=True)
    fine_missing_parts = models.PositiveIntegerField(null=True, blank=True)
    fine_not_working = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

    def adjust_available(self, delta: int):
        """
        Atomic stock adjustment that never allows negative inventory.
        """
        if delta == 0:
            return
        with transaction.atomic():
            locked = Component.objects.select_for_update().get(id=self.id)
            new_value = locked.available_stock + delta
            if new_value < 0:
                raise ValueError("Insufficient stock for adjustment")
            locked.available_stock = new_value
            locked.save(update_fields=["available_stock"])
            # mirror change on instance for callers
            self.available_stock = new_value


class Reservation(models.Model):
    """
    Represents a 15‑minute stock lock for a user/component pair.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservations", db_index=True)
    component = models.ForeignKey(Component, on_delete=models.CASCADE, related_name="reservations")
    quantity = models.PositiveIntegerField()
    reserved_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "component"],
                condition=models.Q(is_active=True),
                name="uniq_active_reservation_per_user_component",
            )
        ]
        indexes = [models.Index(fields=["is_active", "expires_at"])]

    def __str__(self):
        return f"Reservation #{self.id} • {self.component.name} x {self.quantity}"

    def has_expired(self):
        return self.is_active and timezone.now() >= self.expires_at

    def expire_and_release(self):
        """
        Mark inactive and return stock if still locked.
        """
        if not self.is_active:
            return
        with transaction.atomic():
            locked = Reservation.objects.select_for_update().get(id=self.id)
            if not locked.is_active:
                return
            locked.is_active = False
            locked.save(update_fields=["is_active"])
            locked.component.adjust_available(int(locked.quantity))
