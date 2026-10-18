import io
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from .availability import catalog_availability
from .models import Brand, Device, DeviceImage, DeviceVariant, MarketPriceObservation, ResearchSource
from .search import search_local_catalog


SNAPSHOT = Path(__file__).parent / "data" / "pakistan-2026-10-18.json"
OBSERVED = parse_datetime("2026-10-17T20:40:35Z")


@override_settings(GEMINI_WEB_RESEARCH_ENABLED=False, GEMINI_AUTO_RESEARCH_ENABLED=False)
class CatalogReadinessTests(TestCase):
    def test_empty_catalog_is_distinct_from_no_matching_filters(self):
        response = APIClient().get("/api/catalog/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["catalog_status"], "empty")
        self.assertFalse(response.data["research_available"])
        self.assertFalse(response.data["automatic_research"])
        self.assertEqual(search_local_catalog({})["catalog_status"], "empty")
        with patch("recommendations.views.PakistanConversationView.throttle_classes", []):
            response = APIClient().post("/api/recommendations/converse/", {
                "message": "Samsung under PKR 120000", "use_memory": False,
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no published phones", response.data["explanation"])
        self.assertNotIn("Request Gemini web research", response.data["explanation"])

    def test_unpublished_catalog_does_not_leak_readiness(self):
        brand = Brand.objects.create(name="Private", slug="private")
        device = Device.objects.create(brand=brand, name="Private", slug="private")
        self.assertEqual(catalog_availability(), "empty")
        device.is_published = True
        device.save()
        self.assertEqual(catalog_availability(), "missing_prices")

    @override_settings(GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test", GEMINI_CHAT_MODEL="test-model")
    def test_research_capability_exposes_no_credentials(self):
        response = APIClient().get("/api/catalog/status/")
        self.assertTrue(response.data["research_available"])
        self.assertEqual(set(response.data), {"catalog_status", "research_available", "automatic_research", "ai_provider", "search_provider", "guidance_available", "configuration_error"})


class MarketSnapshotTests(TestCase):
    def setUp(self):
        frozen = patch("django.utils.timezone.now", return_value=OBSERVED + timedelta(hours=1))
        frozen.start()
        self.addCleanup(frozen.stop)
        call_command("import_market_snapshot", SNAPSHOT, stdout=io.StringIO())

    def test_import_is_idempotent_and_does_not_refresh_old_evidence(self):
        call_command("import_market_snapshot", SNAPSHOT, stdout=io.StringIO())
        self.assertEqual(Device.objects.count(), 5)
        self.assertEqual(Brand.objects.count(), 3)
        self.assertEqual(MarketPriceObservation.objects.count(), 8)
        self.assertEqual(set(MarketPriceObservation.objects.values_list("observed_at", flat=True)), {OBSERVED})
        self.assertFalse(MarketPriceObservation.objects.exclude(pta_status="unknown").exists())
        self.assertFalse(DeviceVariant.objects.exclude(camera_score=0).exists())
        self.assertEqual(catalog_availability(), "ready")

    def test_samsung_budget_search_has_real_prices_and_excludes_discontinued_listing(self):
        result = search_local_catalog({"brand": "samsung", "budget_pkr": 120000})
        self.assertEqual(result["count"], 3)
        a26 = next(row for row in result["results"] if row["slug"] == "samsung-galaxy-a26")
        self.assertEqual(a26["price_observation"]["observed_min_pkr"], "94999.00")
        self.assertEqual(a26["price_observation"]["source_url"], "https://www.whatmobile.com.pk/Samsung_Galaxy-A26")
        self.assertEqual(search_local_catalog({"city": "Lahore"})["count"], 0)
        self.assertEqual(search_local_catalog({"pta_status": "approved"})["count"], 0)
        self.assertEqual(search_local_catalog({}, as_of=OBSERVED + timedelta(days=31))["count"], 0)

    def test_images_fill_existing_phones_without_overwriting_admin_artwork(self):
        device = Device.objects.get(slug="samsung-galaxy-a16")
        expected = device.primary_image_url
        device.primary_image_url = ""
        device.save()
        call_command("import_market_snapshot", SNAPSHOT, stdout=io.StringIO())
        device.refresh_from_db()
        self.assertEqual(device.primary_image_url, expected)
        self.assertEqual(DeviceImage.objects.count(), 5)
        device.primary_image_url = "https://example.org/custom-phone.jpg"
        device.save()
        call_command("import_market_snapshot", SNAPSHOT, stdout=io.StringIO())
        device.refresh_from_db()
        self.assertEqual(device.primary_image_url, "https://example.org/custom-phone.jpg")
        self.assertEqual(DeviceImage.objects.count(), 5)

    def test_expanded_catalog_has_images_and_distinct_paginated_results(self):
        extra = SNAPSHOT.with_name("pakistan-more-2026-10-18.json")
        call_command("import_market_snapshot", extra, stdout=io.StringIO())
        call_command("import_market_snapshot", extra, stdout=io.StringIO())
        self.assertEqual(Device.objects.count(), 12)
        self.assertEqual(Brand.objects.count(), 7)
        self.assertEqual(DeviceImage.objects.count(), 12)
        self.assertEqual(MarketPriceObservation.objects.count(), 16)
        self.assertFalse(Device.objects.filter(primary_image_url="").exists())
        first = search_local_catalog({"page_size": 9, "page": 1})
        second = search_local_catalog({"page_size": 9, "page": 2})
        self.assertEqual(first["count"], 12)
        self.assertEqual(len(first["results"]), 9)
        self.assertEqual(len(second["results"]), 3)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        detail = APIClient().get("/api/catalog/devices/vivo-v60-lite/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["images"][0]["image_url"], detail.data["primary_image_url"])

    def test_reimport_preserves_review_decisions(self):
        source = ResearchSource.objects.first()
        source.reuse_status = "restricted"
        source.save()
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("import_market_snapshot", SNAPSHOT, stdout=io.StringIO())
        source.refresh_from_db()
        self.assertEqual(source.reuse_status, "restricted")
