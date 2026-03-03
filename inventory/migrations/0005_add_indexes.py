from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0004_alter_component_available_stock_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="reservation",
            name="user",
            field=models.ForeignKey(on_delete=models.CASCADE, related_name="reservations", to=settings.AUTH_USER_MODEL, db_index=True),
        ),
    ]
