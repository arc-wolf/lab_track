from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from secrets import token_hex
import re
from .models import Profile, Group
from django.utils.text import slugify


PHONE_REGEX = re.compile(r"^\+?[0-9]{10,15}$")


def normalize_phone(raw_value: str) -> str:
    value = (raw_value or "").strip().replace(" ", "").replace("-", "")
    return value


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Use your @amrita.edu organization email.")
    full_name = forms.CharField(required=True, max_length=150, label="Full Name")
    semester = forms.CharField(required=False, max_length=20)
    student_class = forms.CharField(required=False, max_length=50, label="Class")
    # group flow
    group_mode = forms.ChoiceField(
        choices=(("create", "Create new group"), ("join", "Join existing group")),
        required=False,
        initial="create",
        label="Group Mode",
    )
    join_group_code = forms.CharField(required=False, max_length=50, label="Group Code to Join")
    group_name = forms.CharField(required=False, max_length=100, label="Group Name (students)")
    phone = forms.CharField(required=False, max_length=20, label="Phone")
    faculty_incharge = forms.ModelChoiceField(
        required=False,
        queryset=Profile.objects.none(),
        empty_label="Select faculty",
        label="Faculty Incharge (for students)",
    )
    # retained for backward compat; now set internally
    group_id = forms.CharField(required=False, max_length=50, widget=forms.HiddenInput())

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
            "group_mode",
            "join_group_code",
            "group_id",
            "group_name",
            "faculty_incharge",
        )

    def clean_username(self):
        raw_username = (self.cleaned_data.get("username") or "").strip()
        if raw_username:
            return raw_username

        full_name = (self.data.get("full_name") or "").strip()
        if not full_name:
            raise forms.ValidationError("Full name is required.")

        base = slugify(full_name).replace("-", ".")[:130] or "user"
        candidate = base
        suffix = 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix += 1
            candidate = f"{base}.{suffix}"[:150]
        return candidate

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if email.endswith("@am.amrita.edu"):
            self.cleaned_data["derived_role"] = Profile.ROLE_FACULTY
        elif email.endswith("@am.students.amrita.edu"):
            self.cleaned_data["derived_role"] = Profile.ROLE_STUDENT
        else:
            raise forms.ValidationError("Use an Amrita organization email.")
        return email

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone", ""))
        if phone and not PHONE_REGEX.match(phone):
            raise forms.ValidationError("Enter a valid phone number (10-15 digits, optional leading +).")
        return phone

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("derived_role")
        if role == Profile.ROLE_STUDENT:
            for field in ("semester", "student_class", "group_id"):
                cleaned.setdefault(field, "")
            mode = cleaned.get("group_mode") or "create"
            if mode not in ("create", "join"):
                self.add_error("group_mode", "Choose create or join.")
            if not cleaned.get("phone"):
                self.add_error("phone", "Required for students.")
            if not cleaned.get("full_name"):
                self.add_error("full_name", "Required for students.")
            if mode == "create":
                if not cleaned.get("group_name"):
                    self.add_error("group_name", "Group name required when creating.")
                if not cleaned.get("faculty_incharge"):
                    self.add_error("faculty_incharge", "Faculty incharge required when creating.")
                elif cleaned.get("faculty_incharge").role != Profile.ROLE_FACULTY:
                    self.add_error("faculty_incharge", "Select a valid faculty incharge.")
            elif mode == "join":
                code = (cleaned.get("join_group_code") or "").strip()
                if not code:
                    self.add_error("join_group_code", "Enter the group code to join.")
                else:
                    group = Group.objects.filter(code__iexact=code).first()
                    if not group:
                        self.add_error("join_group_code", "No group found with this code.")
                    else:
                        cleaned["join_group_code"] = group.code
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
            mode = self.cleaned_data.get("group_mode") or "create"
            if role == Profile.ROLE_STUDENT:
                if mode == "create":
                    # generate unique 6-char code
                    code = token_hex(3).upper()
                    while Group.objects.filter(code=code).exists():
                        code = token_hex(3).upper()
                    profile.group_id = code
                    profile.group_name = self.cleaned_data.get("group_name", "")
                else:
                    profile.group_id = (self.cleaned_data.get("join_group_code") or "").strip().upper()
                    profile.group_name = ""
            profile.phone = self.cleaned_data.get("phone", "")
            selected_faculty = self.cleaned_data.get("faculty_incharge")
            profile.faculty_incharge = selected_faculty.user.username if selected_faculty else ""
            profile.full_name = full_name
            profile.save()
        return user

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].required = False
        self.fields["username"].widget = forms.HiddenInput()
        common_classes = "form-control form-control-lg neo-input"
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {common_classes}".strip()
            field.widget.attrs.setdefault("placeholder", field.label)
        if "phone" in self.fields:
            self.fields["phone"].widget.attrs.update(
                {
                    "inputmode": "tel",
                    "pattern": r"^\+?[0-9]{10,15}$",
                    "placeholder": "+919876543210",
                }
            )
        faculty_qs = (
            Profile.objects.filter(role=Profile.ROLE_FACULTY)
            .select_related("user")
            .order_by("full_name", "user__username")
        )
        self.fields["faculty_incharge"].queryset = faculty_qs
        self.fields["faculty_incharge"].label_from_instance = (
            lambda profile: profile.full_name or profile.user.get_full_name() or profile.user.username
        )
        # Distinguish password fields for better UX
        for pwd in ("password1", "password2"):
            if pwd in self.fields:
                self.fields[pwd].widget.attrs["autocomplete"] = "new-password"


class FullNameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Full Name or Email",
        max_length=150,
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )

    def clean(self):
        entered_identity = (self.cleaned_data.get("username") or "").strip()
        if entered_identity:
            if "@" in entered_identity:
                email_matches = User.objects.filter(email__iexact=entered_identity).distinct()
                match_count = email_matches.count()
                if match_count == 1:
                    self.cleaned_data["username"] = email_matches.first().username
                elif match_count > 1:
                    raise forms.ValidationError(
                        "Multiple accounts use this email. Contact lab admin to resolve duplication."
                    )
            else:
                name_matches = User.objects.filter(profile__full_name__iexact=entered_identity).distinct()
                match_count = name_matches.count()
                if match_count == 1:
                    self.cleaned_data["username"] = name_matches.first().username
                elif match_count > 1:
                    raise forms.ValidationError(
                        "Multiple accounts use this full name. Contact lab admin to resolve duplication."
                    )
        return super().clean()


class OTPVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        label="6-digit OTP",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg neo-input",
                "placeholder": "Enter 6-digit OTP",
                "inputmode": "numeric",
                "pattern": r"\d{6}",
            }
        ),
    )


class PasswordResetOTPRequestForm(forms.Form):
    email = forms.EmailField(
        label="Registered Email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control form-control-lg neo-input",
                "placeholder": "you@amrita.edu",
            }
        ),
    )


class PasswordResetOTPConfirmForm(OTPVerificationForm):
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(
            attrs={"class": "form-control form-control-lg neo-input", "autocomplete": "new-password"}
        ),
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(
            attrs={"class": "form-control form-control-lg neo-input", "autocomplete": "new-password"}
        ),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "Passwords do not match.")
        return cleaned
