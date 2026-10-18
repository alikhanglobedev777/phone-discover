"""Fail-closed, read-only preflight for Phone Discover releases.

Never prints environment variable values, secrets, URLs, or database errors.
This does not deploy, modify tables, fetch external URLs, or call Gemini.
"""

import ipaddress
import re
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Q


def _safe_https_origin(origin):
    try:
        parsed = urlsplit(origin)
        # Accessing parsed.port also validates a malformed or out-of-range port.
        port = parsed.port
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and (port is None or port > 0)
            and not parsed.username
            and not parsed.password
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
            and _public_host(parsed.hostname)
        )
    except ValueError:
        return False


def _public_host(host):
    if not isinstance(host, str) or "*" in host or host.startswith("."):
        return False
    value = host.strip().rstrip(".")
    try:
        return ipaddress.ip_address(value.strip("[]")).is_global
    except ValueError:
        return (bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]", value))
                and "." in value and not value.lower().endswith(
                    (".local", ".internal", ".localhost", ".test")))


def production_configuration_issues():
    """Return only generic configuration diagnoses, never private values."""
    issues = []
    if settings.DEBUG:
        issues.append("Set DJANGO_DEBUG=0.")
    hosts = settings.ALLOWED_HOSTS
    if not hosts or any("*" in h for h in hosts) or not any(_public_host(h) for h in hosts):
        issues.append("Configure at least one explicit public DJANGO_ALLOWED_HOSTS hostname; no wildcard.")
    if settings.SECRET_KEY.startswith("django-insecure-"):
        issues.append("Replace the Django development secret key before production.")
    if not getattr(settings, "SECURE_SSL_REDIRECT", False):
        issues.append("Enable DJANGO_SECURE_SSL_REDIRECT after configuring HTTPS termination.")
    if getattr(settings, "SECURE_HSTS_SECONDS", 0) < 300:
        issues.append("Configure DJANGO_HSTS_SECONDS (at least 300) after verifying HTTPS.")
    if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
        issues.append("Require Secure session and CSRF cookies.")
    if not settings.AUTH_PASSWORD_VALIDATORS:
        issues.append("Enable Django password validators for production admin accounts.")
    if any(not _safe_https_origin(origin) for origin in settings.CORS_ALLOWED_ORIGINS):
        issues.append("Use only HTTPS public CORS origins (or none for same-origin deployments).")
    if any(not _safe_https_origin(origin) for origin in settings.CSRF_TRUSTED_ORIGINS):
        issues.append("Use only HTTPS public CSRF trusted origins (or none for same-origin deployments).")
    if settings.CACHES.get("default", {}).get("BACKEND") != "django.core.cache.backends.redis.RedisCache":
        issues.append("Enable DJANGO_USE_REDIS_CACHE=1 for shared production rate limiting.")
    return issues


class Command(BaseCommand):
    help = "Read-only release preflight; --production enforces HTTPS and shared throttling settings."

    def add_arguments(self, parser):
        parser.add_argument("--production", action="store_true", help="Require public deployment safeguards.")
        parser.add_argument("--database", action="store_true", help="Check DB connectivity and applied migrations.")
        parser.add_argument("--cache", action="store_true", help="Read/write/delete one temporary cache key.")
        parser.add_argument("--require-market-data", action="store_true", help="Require eligible published PKR evidence (implies --database).")

    def handle(self, *args, **options):
        issues = production_configuration_issues() if options["production"] else []
        if options["production"] and not options["cache"]:
            issues.append("Run --production with --cache to verify shared Redis connectivity.")

        if options["database"] or options["require_market_data"]:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                from django.db.migrations.executor import MigrationExecutor
                executor = MigrationExecutor(connection)
                targets = executor.loader.graph.leaf_nodes()
                if executor.migration_plan(targets):
                    issues.append("Database migrations are pending; run manage.py migrate.")
                else:
                    self.stdout.write("PASS: database and migrations")
            except Exception:
                issues.append("Database unreachable or migration state unavailable. Check database configuration and logs.")

        if options["cache"]:
            try:
                cache = caches["default"]
                key = "release-check-" + uuid4().hex
                cache.set(key, "ok", timeout=5)
                if cache.get(key) != "ok":
                    raise ValueError("cache roundtrip failed")
                cache.delete(key)
                self.stdout.write("PASS: cache roundtrip")
            except Exception:
                issues.append("Cache roundtrip failed. Check Redis/cache service and configuration.")

        if options["require_market_data"] and not any("Database" in issue for issue in issues):
            try:
                from catalog.pricing import eligible_price_observations
                has_evidence = (eligible_price_observations()
                                .filter(variant__device__is_published=True)
                                .filter(Q(source__isnull=False) | Q(notes__regex=r"\S"))
                                .exists())
                if has_evidence:
                    self.stdout.write("PASS: at least one eligible published PKR observation")
                else:
                    issues.append("No eligible published PKR price evidence. Review and publish real source-backed observations.")
            except Exception:
                issues.append("Market evidence check unavailable. Check database and catalog migrations.")

        if issues:
            for issue in issues:
                self.stderr.write("FAIL: " + issue)
            raise CommandError(f"Release preflight failed ({len(issues)} check(s)).")
        if options["production"]:
            self.stdout.write(self.style.SUCCESS("PASS: production configuration preflight"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS: local release preflight"))
        self.stdout.write("Provider calls: none; catalog writes: none.")
