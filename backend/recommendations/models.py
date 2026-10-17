import uuid

from django.db import models


class RecommendationQuery(models.Model):
    class ResponseSource(models.TextChoices):
        DETERMINISTIC = "deterministic", "Deterministic"
        GEMINI = "gemini", "Gemini"
        OPENAI = "openai", "OpenAI"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    query_text = models.CharField(max_length=500, blank=True)
    country_code = models.CharField(max_length=2, default="US")
    currency = models.CharField(max_length=3, default="USD")
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    priorities = models.JSONField(default=list, blank=True)
    criteria = models.JSONField(default=dict, blank=True)
    results = models.JSONField(default=list, blank=True)
    result_count = models.PositiveSmallIntegerField(default=0)
    response_source = models.CharField(
        max_length=20,
        choices=ResponseSource.choices,
        default=ResponseSource.DETERMINISTIC,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["country_code", "created_at"],
                name="recommend_country_created_idx",
            ),
            models.Index(
                fields=["response_source", "created_at"],
                name="recommend_source_created_idx",
            ),
        ]

    def __str__(self):
        return f"{self.country_code} recommendation at {self.created_at:%Y-%m-%d %H:%M}"


class ConversationContext(models.Model):
    """Guest conversation preferences addressed by an unguessable UUID handle."""

    session_id = models.UUIDField(primary_key=True, editable=False)
    preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversation {self.session_id}"
