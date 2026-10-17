from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("recommendations", "0003_conversation_context"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchJob",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("criteria", models.JSONField(default=dict)),
                ("status", models.CharField(max_length=12, choices=[("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="queued", db_index=True)),
                ("counts", models.JSONField(default=dict, blank=True)),
                ("notice", models.CharField(max_length=160, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("started_at", models.DateTimeField(null=True, blank=True)),
                ("finished_at", models.DateTimeField(null=True, blank=True)),
                ("requested_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name="research_jobs", null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="researchjob",
            index=models.Index(fields=["status", "created_at"], name="recommend_job_status_idx"),
        ),
    ]
