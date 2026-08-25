from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Device, DeviceImage, SpecificationSection


class CatalogApiTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.client = APIClient()

    def test_published_devices_are_listed(self):
        response = self.client.get("/api/catalog/devices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], Device.objects.filter(is_published=True).count())

    def test_device_detail_contains_variants_and_offers(self):
        device = Device.objects.get(slug="atlas-play-5g")
        response = self.client.get(f"/api/catalog/devices/{device.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["variants"]), 1)
        self.assertEqual(len(response.data["variants"][0]["offers"]), 1)
        self.assertEqual(
            len(response.data["specification_sections"]),
            SpecificationSection.objects.filter(device=device).count(),
        )
        self.assertEqual(
            len(response.data["images"]),
            DeviceImage.objects.filter(device=device).count(),
        )

    def test_devices_can_be_filtered_by_budget_and_gaming_score(self):
        response = self.client.get(
            "/api/catalog/devices/",
            {"price_max": 450, "gaming_score_min": 90, "country": "US"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([device["slug"] for device in response.data["results"]], ["atlas-play-5g"])

    def test_list_exposes_status_and_primary_image(self):
        response = self.client.get("/api/catalog/devices/", {"brand": "nova"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], Device.Status.AVAILABLE)
        self.assertTrue(response.data["results"][0]["primary_image_url"])
