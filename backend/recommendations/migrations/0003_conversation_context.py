from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0002_alter_recommendationquery_response_source")]

    operations = [
        migrations.CreateModel(
            name="ConversationContext",
            fields=[
                ("session_id", models.UUIDField(primary_key=True, editable=False, serialize=False)),
                ("preferences", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
