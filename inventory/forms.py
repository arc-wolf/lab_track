from django import forms

from .models import Component


class ComponentForm(forms.ModelForm):
    class Meta:
        model = Component
        fields = ["name", "category", "total_stock", "available_stock", "student_limit", "faculty_limit"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "total_stock": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "available_stock": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "student_limit": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "faculty_limit": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get("total_stock")
        available = cleaned.get("available_stock")
        if total is not None and available is not None and available > total:
            self.add_error("available_stock", "Available stock cannot exceed total stock.")
        return cleaned
