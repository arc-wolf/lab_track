from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_group_groupmember'),
        ('requests_app', '0003_borrowrequest_due_date_borrowrequest_reminder_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowrequest',
            name='group',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='borrow_requests', to='users.group'),
        ),
    ]
