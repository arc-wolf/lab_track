from django.db import models
from django.contrib.auth.models import User


class Component(models.Model):
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, default="")
    total_stock = models.IntegerField(default=0)
    available_stock = models.IntegerField(default=0)
    student_limit = models.IntegerField(default=0)  # 0 means no per-student limit
    faculty_limit = models.IntegerField(default=0)  # reserved for future faculty requests

    def __str__(self):
        return self.name


class CartItem(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    component = models.ForeignKey(Component, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    slip_generated = models.BooleanField(default=False)

    class Meta:
        unique_together = ("student", "component")

    def __str__(self):
        return f"{self.student.username} - {self.component.name}"
