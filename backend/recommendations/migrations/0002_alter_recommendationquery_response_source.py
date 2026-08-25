from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("recommendations", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recommendationquery",
            name="response_source",
            field=models.CharField(
                choices=[
                    ("deterministic", "Deterministic"),
                    ("gemini", "Gemini"),
                    ("openai", "OpenAI"),
                ],
                default="deterministic",
                max_length=20,
            ),
        ),
    ]
