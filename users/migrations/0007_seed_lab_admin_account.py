from django.db import migrations


def seed_lab_admin(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("users", "Profile")
    make_password = __import__("django.contrib.auth.hashers", fromlist=["make_password"]).make_password

    username = "lab_admin"
    password = "adminpass"

    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "is_staff": True,
            "is_superuser": True,
            "email": "",
        },
    )
    User.objects.filter(pk=user.pk).update(
        is_staff=True,
        is_superuser=True,
        password=make_password(password),
    )
    profile, _ = Profile.objects.get_or_create(user=user)
    if profile.role != "admin":
        profile.role = "admin"
        profile.save(update_fields=["role"])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0006_seed_lab_admin"),
    ]

    operations = [
        migrations.RunPython(seed_lab_admin, noop_reverse),
    ]

