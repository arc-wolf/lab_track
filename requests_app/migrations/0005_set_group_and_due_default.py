from django.db import migrations
from datetime import timedelta
from django.utils import timezone


def set_defaults(apps, schema_editor):
    BorrowRequest = apps.get_model("requests_app", "BorrowRequest")
    Group = apps.get_model("users", "Group")
    for br in BorrowRequest.objects.all():
        if br.created_at and not br.due_date:
            br.due_date = (br.created_at + timedelta(days=45)).date()
        if not br.group and br.student_id:
            profile = getattr(br.student, "profile", None)
            if profile and profile.group_id:
                group = Group.objects.filter(code=profile.group_id).first()
                if group:
                    br.group = group
        br.save(update_fields=["due_date", "group"])


class Migration(migrations.Migration):
    dependencies = [
        ('requests_app', '0004_borrowrequest_group'),
        ('users', '0004_group_groupmember'),
    ]

    operations = [
        migrations.RunPython(set_defaults, migrations.RunPython.noop),
    ]
