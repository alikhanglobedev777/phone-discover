from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import ConversationContext


class Command(BaseCommand):
    help = "Remove expired anonymous conversation preferences (does not remove analytics)."

    def handle(self, *args, **options):
        days = max(1, min(90, int(getattr(settings, "CONVERSATION_RETENTION_DAYS", 7))))
        removed, _ = ConversationContext.objects.filter(
            updated_at__lt=timezone.now() - timedelta(days=days)
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {removed} expired conversation context records."))
