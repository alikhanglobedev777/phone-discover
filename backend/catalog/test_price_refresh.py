"""No external network calls in these backend regression tests."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Brand, Device, DeviceVariant, MarketPriceObservation, PriceRefreshRun, ResearchSource
from .price_refresh import _save_observation, valid_for_variant


class PriceRefreshValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        brand = Brand.objects.create(name="Samsung", slug="samsung")
        cls.device = Device.objects.create(brand=brand, name="Galaxy A36", slug="samsung-galaxy-a36", is_published=True)
        cls.variant = DeviceVariant.objects.create(device=cls.device, name="8/256", ram_gb=8, storage_gb=256)
        cls.url = "https://www.priceoye.pk/mobiles/samsung/samsung-galaxy-a36"

    def phone(self, **overrides):
        doc = {
            "brand": "Samsung", "name": "Galaxy A36", "ram_gb": 8, "storage_gb": 256,
            "source_url": self.url, "price_min_pkr": "107999", "price_max_pkr": "107999",
            "condition": "box_pack", "pta_status": "unknown", "listing_status": "active", "city": "",
        }
        doc.update(overrides)
        return doc

    @override_settings(GEMINI_RESEARCH_SOURCE_DOMAINS=("priceoye.pk", "whatmobile.com.pk"))
    def test_identity_price_condition_and_source_must_match(self):
        with self.assertRaises(ValueError):
            valid_for_variant(self.phone(storage_gb=128), {self.url}, self.variant)
        with self.assertRaises(ValueError):
            valid_for_variant(self.phone(name="Galaxy S25"), {self.url}, self.variant)
        with self.assertRaises(ValueError):
            valid_for_variant(self.phone(condition="used"), {self.url}, self.variant)
        with self.assertRaises(ValueError):
            valid_for_variant(self.phone(listing_status="ended"), {self.url}, self.variant)
        with self.assertRaises(ValueError):
            valid_for_variant(self.phone(), set(), self.variant)
        self.assertEqual(valid_for_variant(self.phone(), {self.url}, self.variant)["storage"], 256)

    def facts(self, amount="107999"):
        return {
            "url": self.url, "minimum": Decimal(amount), "maximum": Decimal(amount),
            "pta": "unknown", "city": "", "listing": "active",
        }

    def test_new_source_requires_permission_and_preserves_reviewed_prices(self):
        now = timezone.now()
        self.assertEqual(_save_observation(self.variant, self.facts(), now=now), "blocked_sources")
        source = ResearchSource.objects.get(url=self.url)
        source.reuse_status = ResearchSource.ReuseStatus.PERMITTED
        source.reuse_notes = "Administrator confirmed intended limited data use."
        source.save()
        self.assertEqual(_save_observation(self.variant, self.facts(), now=now), "observations_added")
        self.assertEqual(_save_observation(self.variant, self.facts(), now=now), "unchanged")
        self.assertEqual(_save_observation(self.variant, self.facts("1000"), now=now + timedelta(days=2)), "rejected")
        self.assertEqual(_save_observation(self.variant, self.facts(), now=now + timedelta(days=2)), "observations_added")
        self.assertEqual(MarketPriceObservation.objects.count(), 2)
        self.assertTrue(all(
            row.verification_status == "web_reported" and row.reviewed_at is None
            for row in MarketPriceObservation.objects.all()
        ))


class PriceRefreshAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="refresh-admin", email="refresh-admin@example.test", password="test-only-credential"
        )
        cls.staff = get_user_model().objects.create_user(
            username="refresh-staff", password="test-only-credential", is_staff=True
        )

    def test_refresh_button_requires_post_superuser_and_valid_settings(self):
        url = reverse("admin:catalog_pricerefreshrun_refresh_now")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        with override_settings(PRICE_REFRESH_ENABLED=False):
            self.assertEqual(self.client.post(url).status_code, 302)
            self.assertFalse(PriceRefreshRun.objects.exists())
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(url).status_code, 403)

    @override_settings(PRICE_REFRESH_ENABLED=True)
    @patch("catalog.price_refresh_admin.launch_async", return_value=True)
    @patch("catalog.price_refresh_admin.research_available", return_value=True)
    def test_admin_click_queues_single_run(self, research_available, launch_async):
        self.client.force_login(self.admin)
        url = reverse("admin:catalog_pricerefreshrun_refresh_now")
        self.assertEqual(self.client.post(url).status_code, 302)
        run = PriceRefreshRun.objects.get()
        self.assertEqual(run.status, "queued")
        self.assertTrue(run.force)
        self.assertEqual(run.requested_by, self.admin)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(PriceRefreshRun.objects.count(), 1)
        launch_async.assert_called_once()
