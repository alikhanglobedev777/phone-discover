from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0004_research_jobs")]

    operations = [
        migrations.AlterField(
            model_name="recommendationquery",
            name="response_source",
            field=models.CharField(
                choices=[
                    ("deterministic", "Deterministic"),
                    ("gemini", "Gemini"),
                    ("openai", "OpenAI"),
                    ("groq", "Groq"),
                ],
                default="deterministic",
                max_length=20,
            ),
        ),
    ]
