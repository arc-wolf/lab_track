from django.db import migrations


def seed_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("users", "Profile")
    make_password = __import__("django.contrib.auth.hashers", fromlist=["make_password"]).make_password

    username = "admin1"
    password = "adminpass"

    user, created = User.objects.get_or_create(
        username=username,
        defaults={"is_staff": True, "is_superuser": False, "email": ""},
    )

    # Always enforce staff flag
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])

    # Reset password to the configured default so it stays known/alterable later
    hashed = make_password(password)
    User.objects.filter(pk=user.pk).update(password=hashed)

    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.role != "admin":
        profile.role = "admin"
        profile.save(update_fields=["role"])


def unseed_admin(apps, schema_editor):
    # Keep user in place to avoid breaking auth references; no-op rollback.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_profile_group_name"),
    ]

    operations = [
        migrations.RunPython(seed_admin, unseed_admin),
    ]
