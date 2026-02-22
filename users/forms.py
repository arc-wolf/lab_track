from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Use your @amrita.edu organization email.")
    semester = forms.CharField(required=False, max_length=20)
    student_class = forms.CharField(required=False, max_length=50, label="Class")
    group_id = forms.CharField(required=False, max_length=50)
    phone = forms.CharField(required=False, max_length=20, label="Phone")
    faculty_incharge = forms.CharField(required=False, max_length=100, label="Faculty Incharge (for students)")
    full_name = forms.CharField(required=False, max_length=150, label="Full Name (for faculty)")
    group_name = forms.CharField(required=False, max_length=100, label="Group Name (students)")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
            "full_name",
            "phone",
            "semester",
            "student_class",
            "group_id",
            "group_name",
            "faculty_incharge",
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email.endswith("@am.amrita.edu"):
            self.cleaned_data["derived_role"] = Profile.ROLE_FACULTY
        elif email.endswith("@am.students.amrita.edu"):
            self.cleaned_data["derived_role"] = Profile.ROLE_STUDENT
        else:
            raise forms.ValidationError("Use an Amrita organization email.")
        return email

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("derived_role")
        if role == Profile.ROLE_STUDENT:
            for field in ("semester", "student_class", "group_id"):
                if not cleaned.get(field):
                    self.add_error(field, "Required for students.")
            if not cleaned.get("faculty_incharge"):
                self.add_error("faculty_incharge", "Required for students.")
            if not cleaned.get("phone"):
                self.add_error("phone", "Required for students.")
        elif role == Profile.ROLE_FACULTY:
            if not cleaned.get("full_name"):
                self.add_error("full_name", "Required for faculty/staff.")
            if not cleaned.get("phone"):
                self.add_error("phone", "Required for faculty/staff.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        full_name = self.cleaned_data.get("full_name", "")
        if full_name:
            if " " in full_name:
                user.first_name = full_name.split(" ", 1)[0]
                user.last_name = full_name.split(" ", 1)[1]
            else:
                user.first_name = full_name
        if commit:
            user.save()
            profile = user.profile
            role = self.cleaned_data.get("derived_role", Profile.ROLE_STUDENT)
            profile.role = role
            profile.semester = self.cleaned_data.get("semester", "")
            profile.student_class = self.cleaned_data.get("student_class", "")
            profile.group_id = self.cleaned_data.get("group_id", "")
            profile.phone = self.cleaned_data.get("phone", "")
            profile.faculty_incharge = self.cleaned_data.get("faculty_incharge", "")
            profile.full_name = full_name
            profile.group_name = self.cleaned_data.get("group_name", "")
            profile.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        common_classes = "form-control form-control-lg neo-input"
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {common_classes}".strip()
            field.widget.attrs.setdefault("placeholder", field.label)
        # Distinguish password fields for better UX
        for pwd in ("password1", "password2"):
            if pwd in self.fields:
                self.fields[pwd].widget.attrs["autocomplete"] = "new-password"
