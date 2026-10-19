from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_device_gallery_colors"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceRefreshRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(max_length=12, default="queued", db_index=True,
                    choices=[("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")])),
                ("origin", models.CharField(max_length=12, default="cli",
                    choices=[("admin", "Admin button"), ("scheduled", "48-hour scheduler"), ("cli", "Command line")])),
                ("force", models.BooleanField(default=False)),
                ("counts", models.JSONField(blank=True, default=dict)),
                ("notice", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name="price_refresh_runs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-pk"]},
        ),
        migrations.CreateModel(
            name="PriceRefreshCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_attempted_at", models.DateTimeField(db_index=True)),
                ("last_result", models.CharField(max_length=32, blank=True)),
                ("variant", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name="price_refresh_check", to="catalog.devicevariant")),
            ],
        ),
    ]
