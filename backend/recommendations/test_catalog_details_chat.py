"""Exact-model chat should reuse published local specifications without price data."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Brand, Device, DeviceVariant, SpecificationSection, SpecificationItem


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=False, GEMINI_WEB_RESEARCH_ENABLED=False)
class CatalogDetailChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        google = Brand.objects.create(name="Google", slug="google")
        pixel = Device.objects.create(
            brand=google, name="Pixel 7a", slug="google-pixel-7a",
            summary="Saved local Pixel 7a summary", operating_system="Android",
            is_published=True,
        )
        DeviceVariant.objects.create(
            device=pixel, name="8GB/128GB", ram_gb=8, storage_gb=128,
            chipset="Google Tensor G2", battery_mah=4385,
        )
        section = SpecificationSection.objects.create(
            device=pixel, name="Camera", slug="camera",
        )
        SpecificationItem.objects.create(section=section, label="Main camera", value="64 MP")
        Device.objects.create(
            brand=google, name="Pixel 7 Pro", slug="google-pixel-7-pro", is_published=True,
        )

    def test_exact_pixel_returns_catalog_details_without_any_price(self):
        client = APIClient()
        with patch("recommendations.views.research_and_save") as research:
            response = client.post("/api/recommendations/converse/",
                                   {"message": "Google Pixel 7a info"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(len(response.data["catalog_details"]), 1)
        phone = response.data["catalog_details"][0]
        self.assertEqual(phone["name"], "Pixel 7a")
        self.assertEqual(phone["variants"][0]["chipset"], "Google Tensor G2")
        self.assertEqual(phone["specification_sections"][0]["items"][0]["value"], "64 MP")
        self.assertIn("price is not available", response.data["explanation"].lower())
        research.assert_not_called()

    def test_broad_camera_question_does_not_claim_exact_model(self):
        from .local_intent import parse_pakistan_intent
        self.assertNotIn("device_query", parse_pakistan_intent("best camera phone"))
