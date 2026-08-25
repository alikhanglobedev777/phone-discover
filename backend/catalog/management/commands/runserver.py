from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)

from recommendations.providers import get_provider_status


class Command(StaticfilesRunserverCommand):
    """Run Django's development server with a project-friendly status banner."""

    def on_bind(self, server_port):
        super().on_bind(server_port)

        display_host = self.addr
        if display_host in {"0", "0.0.0.0", "::"}:
            display_host = "127.0.0.1"
        elif self.use_ipv6 and not display_host.startswith("["):
            display_host = f"[{display_host}]"

        base_url = f"{self.protocol}://{display_host}:{self.port}"
        assistant = get_provider_status()["label"]
        border = "=" * 68

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(border))
        self.stdout.write(self.style.SUCCESS("  MOBILE DISCOVERY BACKEND IS RUNNING"))
        self.stdout.write(self.style.WARNING(f"  Server : {base_url}/"))
        self.stdout.write(self.style.WARNING(f"  Admin  : {base_url}/admin/"))
        self.stdout.write(self.style.WARNING(f"  API    : {base_url}/api/"))
        self.stdout.write(self.style.WARNING(f"  AI     : {assistant}"))
        self.stdout.write(self.style.SUCCESS("  Stop   : Press CTRL+C"))
        self.stdout.write(self.style.SUCCESS(border))
        self.stdout.write("")
