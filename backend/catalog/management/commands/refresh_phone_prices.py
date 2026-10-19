"""Run one bounded PKR source refresh; designed for Windows Task Scheduler."""

from django.core.management.base import BaseCommand, CommandError
from catalog.models import PriceRefreshRun
from catalog.price_refresh import refresh_run


class Command(BaseCommand):
    help = "Refresh eligible existing exact phone variants from permitted PriceOye/WhatMobile evidence."

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=int, help="Queued admin run ID (never reuse a completed run)")
        parser.add_argument("--limit", type=int, help="Maximum variants; safety cap 250")
        parser.add_argument("--force", action="store_true", help="Ignore the 48-hour due cutoff")
        parser.add_argument("--scheduled", action="store_true", help="Mark this run as a scheduled job")

    def handle(self, *args, **options):
        if options["limit"] is not None and not 1 <= options["limit"] <= 250:
            raise CommandError("--limit must be between 1 and 250")
        if options["run_id"] is not None:
            try:
                run = PriceRefreshRun.objects.get(pk=options["run_id"], status="queued")
            except PriceRefreshRun.DoesNotExist as exc:
                raise CommandError("Queued price refresh run not found") from exc
        else:
            run = PriceRefreshRun.objects.create(
                origin=PriceRefreshRun.Origin.SCHEDULED if options["scheduled"] else PriceRefreshRun.Origin.CLI,
                force=options["force"],
            )
        counts = refresh_run(run, limit=options["limit"])
        run.refresh_from_db()
        self.stdout.write(f"Price refresh #{run.pk}: {run.status}; {counts}; {run.notice}")
        if run.status == PriceRefreshRun.Status.FAILED:
            raise CommandError(run.notice)
