"""Read-only audit command for the evidence review backlog."""
import json

from django.core.management.base import BaseCommand

from catalog.quality import catalog_quality_snapshot


class Command(BaseCommand):
    help = "Show catalog coverage and missing source verification; never edits records."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    def handle(self, *args, **options):
        data = catalog_quality_snapshot()
        if options["json"]:
            self.stdout.write(json.dumps(data, sort_keys=True))
            return
        self.stdout.write("Phone Discover evidence coverage")
        for key, value in data.items():
            self.stdout.write(f"{key}: {value}")
        self.stdout.write(
            "No scores have been generated. Verify sources and claims through "
            "the existing human review process before relying on performance ratings."
        )
