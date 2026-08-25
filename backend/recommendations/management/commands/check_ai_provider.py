from django.core.management.base import BaseCommand, CommandError

from recommendations.providers import get_provider_status, test_provider_connection


class Command(BaseCommand):
    help = "Show the active recommendation explanation provider without exposing API keys."

    def add_arguments(self, parser):
        parser.add_argument(
            "--live",
            action="store_true",
            help="Contact the configured provider to verify the key and model.",
        )

    def handle(self, *args, **options):
        status = get_provider_status()
        style = self.style.SUCCESS if status["configured"] else self.style.WARNING
        self.stdout.write(style(f"AI provider: {status['label']}"))
        self.stdout.write(f"Requested mode: {status['requested']}")
        self.stdout.write(f"Active mode: {status['active']}")
        self.stdout.write("API key loaded: yes" if status["active"] != "deterministic" else "API key loaded: no")

        if options["live"] and status["active"] != "deterministic":
            self.stdout.write("Checking provider connection...")
            try:
                result = test_provider_connection()
            except Exception as exc:
                raise CommandError(
                    "Provider connection failed. Check the key, model, quota, and internet connection. "
                    f"Details: {exc}"
                ) from exc
            self.stdout.write(self.style.SUCCESS(result))
