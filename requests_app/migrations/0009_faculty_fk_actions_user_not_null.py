from django.db import migrations, models
from django.conf import settings
from django.contrib.auth import get_user_model


def forward_fill_user_and_faculty(apps, schema_editor):
    BorrowRequest = apps.get_model("requests_app", "BorrowRequest")
    User = get_user_model()
    fallback_user = User.objects.order_by("id").first()
    if not fallback_user:
        return
    fallback_faculty = User.objects.filter(profile__role="faculty").order_by("id").first() or fallback_user
    for br in BorrowRequest.objects.all():
        # Fill user if missing
        if br.user_id is None:
            br.user_id = fallback_user.id
        # Fill faculty FK from faculty_name if possible
        if getattr(br, "faculty_id", None) is None:
            faculty_name = getattr(br, "faculty_name", "") or ""
            if faculty_name:
                match = User.objects.filter(username=faculty_name).first()
                if match:
                    br.faculty_id = match.id
        if getattr(br, "faculty_id", None) is None:
            br.faculty_id = fallback_faculty.id
        br.save(update_fields=["user_id", "faculty_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("requests_app", "0008_remove_borrowrequest_counsellor_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # add faculty FK (nullable during migration)
        migrations.AddField(
            model_name="borrowrequest",
            name="faculty",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                limit_choices_to={"profile__role": "faculty"},
                related_name="faculty_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # add project_title for clarity
        migrations.AddField(
            model_name="borrowrequest",
            name="project_title",
            field=models.CharField(blank=True, max_length=255),
        ),
        # new audit model
        migrations.CreateModel(
            name="BorrowAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("CREATED", "Created"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("ISSUED", "Issued"), ("RETURNED", "Returned"), ("AUTO_OVERDUE", "Auto Overdue")], max_length=20)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("note", models.TextField(blank=True)),
                ("borrow_request", models.ForeignKey(on_delete=models.CASCADE, related_name="actions", to="requests_app.borrowrequest")),
                ("performed_by", models.ForeignKey(on_delete=models.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        # data migration to fill user/faculty
        migrations.RunPython(forward_fill_user_and_faculty, migrations.RunPython.noop),
        # remove old faculty_name
        migrations.RemoveField(
            model_name="borrowrequest",
            name="faculty_name",
        ),
        # enforce non-null user
        migrations.AlterField(
            model_name="borrowrequest",
            name="user",
            field=models.ForeignKey(on_delete=models.CASCADE, related_name="borrow_requests", to=settings.AUTH_USER_MODEL),
        ),
        # enforce non-null faculty
        migrations.AlterField(
            model_name="borrowrequest",
            name="faculty",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                limit_choices_to={"profile__role": "faculty"},
                related_name="faculty_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # add indexes on status and created_at
        migrations.AlterField(
            model_name="borrowrequest",
            name="status",
            field=models.CharField(db_index=True, choices=[("DRAFT", "Draft"), ("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("ISSUED", "Issued"), ("RETURNED", "Returned"), ("OVERDUE", "Overdue")], default="PENDING", max_length=20),
        ),
        migrations.AlterField(
            model_name="borrowrequest",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        # add index to BorrowItem.component
        migrations.AlterField(
            model_name="borrowitem",
            name="component",
            field=models.ForeignKey(db_index=True, on_delete=models.PROTECT, related_name="borrow_items", to="inventory.component"),
        ),
    ]
