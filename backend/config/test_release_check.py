"""Patch 14: safe preflight assertions, no live Redis/Gemini/Postgres calls."""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from config.management.commands.release_check import (
    _safe_https_origin,
    _public_host,
    production_configuration_issues,
)


class ReleaseCheckTests(SimpleTestCase):
    def test_development_preflight_needs_no_database_or_network(self):
        out = StringIO()
        with patch("config.management.commands.release_check.connection") as conn:
            call_command("release_check", stdout=out)
        conn.cursor.assert_not_called()
        self.assertIn("PASS: local release preflight", out.getvalue())
        self.assertIn("Provider calls: none", out.getvalue())

    @override_settings(
        DEBUG=True, SECRET_KEY="django-insecure-" + "x" * 40,
        ALLOWED_HOSTS=["*"], SECURE_SSL_REDIRECT=False, SECURE_HSTS_SECONDS=0,
        SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
        AUTH_PASSWORD_VALIDATORS=[],
        CORS_ALLOWED_ORIGINS=["http://localhost:5173"],
        CSRF_TRUSTED_ORIGINS=["http://localhost:5173"],
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    )
    def test_production_rejects_development_settings_without_echoing_secrets(self):
        out, err = StringIO(), StringIO()
        with self.assertRaises(CommandError):
            call_command("release_check", production=True, stdout=out, stderr=err)
        message = err.getvalue()
        self.assertIn("DJANGO_DEBUG=0", message)
        self.assertIn("DJANGO_USE_REDIS_CACHE=1", message)
        self.assertIn("--cache", message)
        self.assertIn("HTTPS", message)
        self.assertNotIn("django-insecure-", message)

    def test_https_origin_validation_rejects_local_http_and_credentials(self):
        self.assertTrue(_safe_https_origin("https://www.example.com"))
        for origin in (
            "http://www.example.com", "https://localhost", "https://127.0.0.1", "https://192.168.1.1",
            "https://user:pass@example.com", "https://example.com/private",
            "https://example.com?token=secret", "https://example.com/#fragment",
            "https://example.com:bad",
            "not a url",
        ):
            with self.subTest(origin=origin):
                self.assertFalse(_safe_https_origin(origin))

    @override_settings(
        DEBUG=False, SECRET_KEY="a" * 48, ALLOWED_HOSTS=["phones.example.com"],
        SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=300,
        SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
        AUTH_PASSWORD_VALIDATORS=[{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}],
        CORS_ALLOWED_ORIGINS=["https://phones.example.com"],
        CSRF_TRUSTED_ORIGINS=["https://phones.example.com"],
        CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                            "LOCATION": "redis://localhost:6379/0"}},
    )
    def test_production_flags_and_mocked_shared_cache_pass(self):
        self.assertEqual(production_configuration_issues(), [])
        cache = MagicMock()
        cache.get.return_value = "ok"
        with patch("config.management.commands.release_check.caches") as cache_map:
            cache_map.__getitem__.return_value = cache
            out = StringIO()
            call_command("release_check", production=True, cache=True, stdout=out)
        self.assertIn("PASS: production configuration preflight", out.getvalue())
        cache.set.assert_called_once()
        cache.delete.assert_called_once()

    @override_settings(
        DEBUG=False, SECRET_KEY="a" * 48, ALLOWED_HOSTS=["phones.example.com"],
        SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=300,
        SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
        AUTH_PASSWORD_VALIDATORS=[{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}],
        CORS_ALLOWED_ORIGINS=[], CSRF_TRUSTED_ORIGINS=[],
        CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache",
                            "LOCATION": "redis://localhost:6379/0"}},
    )
    def test_cache_failure_does_not_echo_connection_details(self):
        cache = MagicMock()
        cache.set.side_effect = OSError("redis://private:password@127.0.0.1:6379/0")
        with patch("config.management.commands.release_check.caches") as mapping:
            mapping.__getitem__.return_value = cache
            error = StringIO()
            with self.assertRaises(CommandError):
                call_command("release_check", production=True, cache=True, stderr=error)
        self.assertIn("Cache roundtrip failed", error.getvalue())
        self.assertNotIn("password", error.getvalue())

    def test_database_failure_is_redacted(self):
        error = StringIO()
        with patch("config.management.commands.release_check.connection") as conn:
            conn.cursor.side_effect = OSError("private database password")
            with self.assertRaises(CommandError):
                call_command("release_check", database=True, stderr=error)
        self.assertIn("Database unreachable", error.getvalue())
        self.assertNotIn("private", error.getvalue())

    def test_missing_eligible_market_data_blocks_requested_readiness(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        with patch("config.management.commands.release_check.connection") as conn, \
             patch("django.db.migrations.executor.MigrationExecutor") as executor, \
             patch("catalog.pricing.eligible_price_observations") as eligible:
            conn.cursor.return_value = cursor
            executor.return_value.loader.graph.leaf_nodes.return_value = []
            executor.return_value.migration_plan.return_value = []
            eligible.return_value.filter.return_value.filter.return_value.exists.return_value = False
            err = StringIO()
            with self.assertRaises(CommandError):
                call_command("release_check", require_market_data=True, stderr=err)
        self.assertIn("No eligible published PKR", err.getvalue())

    def test_existing_eligible_market_data_passes_requested_readiness(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        with patch("config.management.commands.release_check.connection") as conn, \
             patch("django.db.migrations.executor.MigrationExecutor") as executor, \
             patch("catalog.pricing.eligible_price_observations") as eligible:
            conn.cursor.return_value = cursor
            executor.return_value.loader.graph.leaf_nodes.return_value = []
            executor.return_value.migration_plan.return_value = []
            eligible.return_value.filter.return_value.filter.return_value.exists.return_value = True
            out = StringIO()
            call_command("release_check", require_market_data=True, stdout=out)
        self.assertIn("at least one eligible published", out.getvalue())

    def test_public_host_check_rejects_internal_only_domains(self):
        for host in ("backend", "localhost", "10.0.0.1", "127.0.0.1", "*.example.com", ".example.com", "internal.local"):
            with self.subTest(host=host):
                self.assertFalse(_public_host(host))
        self.assertTrue(_public_host("phones.example.com"))

    def test_wildcard_host_rejected_even_with_named_host(self):
        with override_settings(ALLOWED_HOSTS=["phones.example.com", "*.example.com"]):
            self.assertTrue(any("DJANGO_ALLOWED_HOSTS" in e for e in production_configuration_issues()))
