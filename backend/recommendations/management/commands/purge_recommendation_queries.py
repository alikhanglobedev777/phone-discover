from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from recommendations.models import RecommendationQuery


class Command(BaseCommand):
    help = "Delete recommendation analytics older than the configured retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=getattr(settings, "RECOMMENDATION_QUERY_RETENTION_DAYS", 90),
        )

    def handle(self, *args, **options):
        days = max(1, options["days"])
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = RecommendationQuery.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} recommendation query records."))
