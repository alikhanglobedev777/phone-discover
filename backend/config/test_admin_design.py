"""Admin theme is purely presentation; staff permissions still control links and data."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from catalog.models import Brand, Device, PriceRefreshRun


class PhoneDiscoverAdminThemeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="theme-admin", email="theme-admin@example.com", password="only-a-test-password"
        )
        cls.staff = get_user_model().objects.create_user(
            username="theme-staff", password="only-a-test-password", is_staff=True
        )
        brand = Brand.objects.create(name="Theme Test", slug="theme-test")
        Device.objects.create(
            brand=brand, name="Example Phone", slug="example-theme-phone", is_published=True
        )

    def test_dashboard_has_branding_and_safe_admin_links(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your catalog, under control.")
        self.assertContains(response, "Phone Discover")
        self.assertContains(response, "Total phones")
        self.assertContains(response, "Published phones")
        self.assertContains(response, "Price refresh runs")
        self.assertContains(response, "catalog/admin/brand_admin.css")
        self.assertContains(response, reverse("admin:catalog_device_changelist"))
        self.assertContains(response, reverse("admin:catalog_pricerefreshrun_changelist"))

    def test_staff_without_model_permissions_does_not_get_private_quick_links_or_counts(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Total phones")
        self.assertNotContains(response, "+ Add a phone")
        self.assertNotContains(response, "Review market prices")

    def test_homepage_does_not_launch_refresh_or_create_runs(self):
        self.client.force_login(self.admin)
        with patch("catalog.price_refresh_admin.launch_async") as launch:
            response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        launch.assert_not_called()
        self.assertEqual(PriceRefreshRun.objects.count(), 0)

    def test_login_page_uses_the_same_branding(self):
        response = self.client.get(reverse("admin:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phone Discover")
        self.assertContains(response, "catalog/admin/brand_admin.css")
