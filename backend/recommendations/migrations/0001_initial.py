import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RecommendationQuery",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("session_id", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("query_text", models.CharField(blank=True, max_length=500)),
                ("country_code", models.CharField(default="US", max_length=2)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("budget", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("priorities", models.JSONField(blank=True, default=list)),
                ("criteria", models.JSONField(blank=True, default=dict)),
                ("results", models.JSONField(blank=True, default=list)),
                ("result_count", models.PositiveSmallIntegerField(default=0)),
                (
                    "response_source",
                    models.CharField(
                        choices=[("deterministic", "Deterministic"), ("openai", "OpenAI")],
                        default="deterministic",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="recommendationquery",
            index=models.Index(
                fields=["country_code", "created_at"],
                name="recommend_country_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="recommendationquery",
            index=models.Index(
                fields=["response_source", "created_at"],
                name="recommend_source_created_idx",
            ),
        ),
    ]
