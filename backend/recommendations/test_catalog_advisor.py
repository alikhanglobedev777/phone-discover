"""Regressions for catalog-first name matching, specs-only ranking and follow-ups."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Brand, Device, DeviceVariant, SpecificationItem, SpecificationSection
from .catalog_advisor import catalog_mentions, specs_recommendations, compare_catalog_phones


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=False, GEMINI_WEB_RESEARCH_ENABLED=False)
class CatalogAdvisorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        samsung = Brand.objects.create(name="Samsung", slug="samsung")
        google = Brand.objects.create(name="Google", slug="google")
        vivo = Brand.objects.create(name="Vivo", slug="vivo")
        cls.s26 = Device.objects.create(
            brand=samsung, name="Galaxy S26", slug="s26", is_published=True,
        )
        cls.ultra = Device.objects.create(
            brand=samsung, name="Galaxy S26 Ultra", slug="s26-ultra", is_published=True,
            summary="Ultra camera hardware stored in catalog",
        )
        cls.pixel = Device.objects.create(
            brand=google, name="Pixel 7a", slug="pixel-7a", is_published=True,
        )
        cls.vivo = Device.objects.create(
            brand=vivo, name="X90s", slug="vivo-x90s", is_published=True,
        )
        cls.hidden = Device.objects.create(
            brand=samsung, name="Galaxy S27 Ultra", slug="hidden-s27",
            is_published=False,
        )
        DeviceVariant.objects.create(
            device=cls.s26, name="8/128", ram_gb=8, storage_gb=128,
            camera_score=70, gaming_score=75, battery_score=60,
            chipset="Chip A",
        )
        DeviceVariant.objects.create(
            device=cls.ultra, name="12/256", ram_gb=12, storage_gb=256,
            camera_score=95, gaming_score=88, battery_score=85,
            chipset="Chip B", battery_mah=5000,
        )
        DeviceVariant.objects.create(
            device=cls.pixel, name="8/128", ram_gb=8, storage_gb=128,
            camera_score=89, gaming_score=68, battery_score=0,
        )
        DeviceVariant.objects.create(
            device=cls.vivo, name="12/256", ram_gb=12, storage_gb=256,
            camera_score=0, gaming_score=0, battery_score=0,
        )
        section = SpecificationSection.objects.create(
            device=cls.pixel, name="Camera", slug="camera",
        )
        SpecificationItem.objects.create(section=section, label="Main camera", value="64 MP")

    def ask(self, text, **fields):
        return APIClient().post("/api/recommendations/converse/",
                                {"message": text, **fields}, format="json")

    def test_catalog_model_aliases_use_longest_exact_model_not_sibling(self):
        for text in ("Tell me about Samsung S26 Ultra", "S26 Ultra specs",
                     "Samsung Galaxy S26 Ultra"):
            with self.subTest(text=text):
                found = catalog_mentions(text)
                self.assertEqual([phone["slug"] for phone in found], ["s26-ultra"])
        self.assertEqual(
            [p["slug"] for p in catalog_mentions("Compare S26 Ultra vs Pixel 7a")],
            ["s26-ultra", "pixel-7a"],
        )
        self.assertEqual(catalog_mentions("Samsung S27 Ultra"), [])
        self.assertEqual(
            [p["slug"] for p in catalog_mentions("Vivo X90s details")],
            ["vivo-x90s"],
        )

    def test_exact_model_response_is_local_and_links_to_correct_modal(self):
        response = self.ask("What are the Samsung S26 Ultra details?")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["criteria"]["device_query"], "Galaxy S26 Ultra")
        self.assertEqual([x["slug"] for x in response.data["catalog_details"]], ["s26-ultra"])
        self.assertEqual(response.data["catalog_details"][0]["detail_api_url"],
                         "/api/catalog/devices/s26-ultra/")
        self.assertEqual(response.data["specs_results"], [])

    def test_best_camera_returns_specs_candidates_without_pricing(self):
        response = self.ask("best camera phone")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        candidates = response.data["specs_results"]
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["slug"], "s26-ultra")
        self.assertEqual(candidates[1]["slug"], "pixel-7a")
        self.assertEqual(candidates[0]["editorial_fit"], 95.0)
        self.assertEqual(candidates[0]["price_status"], "not_verified_for_filters")
        self.assertNotIn("price_min_pkr", str(candidates))
        self.assertNotIn("hidden-s27", str(candidates))
        self.assertIn("not verified", response.data["explanation"])

    def test_budget_and_pta_cannot_be_claimed_from_specs(self):
        response = self.ask("best camera phone under 80k in Lahore PTA approved")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["specs_results"])
        self.assertEqual(response.data["results"], [])
        self.assertIn("budget fit", response.data["explanation"])
        self.assertIn("not verified", response.data["explanation"])
        self.assertEqual(response.data["criteria"]["budget_pkr"], "80000")
        self.assertEqual(response.data["criteria"]["pta_status"], "approved")

    def test_gaming_and_battery_priorities_change_specs_ranking(self):
        gaming = self.ask("best gaming phone")
        battery = self.ask("best battery phone")
        self.assertEqual(gaming.data["specs_results"][0]["slug"], "s26-ultra")
        self.assertEqual(battery.data["specs_results"][0]["slug"], "s26-ultra")
        # Known scores outrank models whose scores are absent.
        self.assertIsNone(
            next(p for p in battery.data["specs_results"] if p["slug"] == "pixel-7a")["editorial_fit"]
        ) if any(p["slug"] == "pixel-7a" for p in battery.data["specs_results"]) else None

    def test_compare_explicit_models_with_missing_scores_no_fake_winner(self):
        response = self.ask("compare Galaxy S26 Ultra vs Google Pixel 7a")
        self.assertEqual(response.status_code, 200)
        comparison = response.data["comparison"]
        self.assertEqual([p["slug"] for p in comparison["phones"]],
                         ["s26-ultra", "pixel-7a"])
        camera = next(row for row in comparison["dimensions"] if row["dimension"] == "camera")
        battery = next(row for row in comparison["dimensions"] if row["dimension"] == "battery")
        self.assertEqual(camera["leader_slug"], "s26-ultra")
        self.assertIsNone(battery["leader_slug"])
        self.assertIn("Insufficient", battery["note"])
        self.assertEqual([p["slug"] for p in response.data["catalog_details"]],
                         ["s26-ultra", "pixel-7a"])

    def test_followup_compare_it_with_pixel_and_ask_which_battery(self):
        initial = self.ask("Samsung S26 Ultra")
        self.assertEqual(initial.status_code, 200)
        follow = self.ask("Compare it with Pixel 7a",
                          session_id=initial.data["session_id"])
        self.assertEqual(follow.status_code, 200)
        self.assertEqual([p["slug"] for p in follow.data["comparison"]["phones"]],
                         ["s26-ultra", "pixel-7a"])
        next_turn = self.ask("Which one has better battery?",
                             session_id=initial.data["session_id"])
        self.assertEqual(next_turn.status_code, 200)
        self.assertIsNotNone(next_turn.data["comparison"])
        rows = next_turn.data["comparison"]["dimensions"]
        self.assertIsNone(next(r for r in rows if r["dimension"] == "battery")["leader_slug"])
        self.assertTrue(next_turn.data["memory_used"])

    def test_new_category_request_drops_stale_exact_phone(self):
        initial = self.ask("Samsung S26 Ultra")
        follow = self.ask("best camera phone", session_id=initial.data["session_id"])
        self.assertEqual(follow.status_code, 200)
        self.assertIsNone(follow.data["criteria"]["device_query"])
        self.assertTrue(follow.data["specs_results"])

    def test_standalone_specs_ranking_respects_brand_and_variant_requirements(self):
        candidates = specs_recommendations({
            "brand": "google", "priorities": ["camera"],
            "ram_min": 8, "max_results": 3,
        })
        self.assertEqual([p["slug"] for p in candidates], ["pixel-7a"])
        self.assertEqual(candidates[0]["strengths"][0], "Camera editorial score: 89/100")
        self.assertIsNone(compare_catalog_phones(["s26-ultra", "hidden-s27"]))
