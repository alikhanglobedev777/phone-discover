from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from recommendations.models import ResearchJob


class Command(BaseCommand):
    help = "Delete old research job metadata and fail stale unfinished jobs."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, *args, **options):
        days = options["days"]
        if not 1 <= days <= 365:
            raise ValueError("days must be between 1 and 365")
        now = timezone.now()
        cutoff = now - timedelta(days=days)
        stale = ResearchJob.objects.filter(status__in=["queued", "running"], created_at__lt=now - timedelta(hours=2))
        failed = stale.update(status="failed", finished_at=now, notice="Job timed out; request fresh research if needed.")
        deleted, _ = ResearchJob.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Marked {failed} stale job(s) failed; deleted {deleted} old row(s).")
