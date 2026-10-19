from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Brand, Device, DeviceColor, DeviceImage


class DeviceGalleryTests(TestCase):
    def setUp(self):
        brand = Brand.objects.create(name="Example", slug="example")
        self.device = Device.objects.create(brand=brand, name="Example One", slug="example-one", is_published=True)

    def test_gallery_details_expose_exact_views_and_finishes(self):
        color = DeviceColor.objects.create(device=self.device, name="Deep Red", hex_code="#84293F")
        DeviceImage.objects.create(
            device=self.device, image_url="https://example.org/front.jpg", view="front", color=color, is_primary=True,
        )
        DeviceImage.objects.create(
            device=self.device, image_url="https://example.org/back.jpg", view="back", color=color,
        )
        DeviceImage.objects.create(device=self.device, image_url="https://example.org/side.jpg", view="side")
        response = APIClient().get(f"/api/catalog/devices/{self.device.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["colors"][0]["name"], "Deep Red")
        self.assertEqual(response.data["colors"][0]["hex_code"], "#84293F")
        self.assertEqual({im["view"] for im in response.data["images"]}, {"front", "back", "side"})
        self.assertEqual(next(im for im in response.data["images"] if im["view"] == "front")["color"], color.pk)

    def test_photo_color_must_belong_to_phone(self):
        other = Device.objects.create(brand=self.device.brand, name="Other", slug="other")
        color = DeviceColor.objects.create(device=other, name="Silver")
        image = DeviceImage(device=self.device, image_url="https://example.org/photo.jpg", color=color)
        with self.assertRaises(ValidationError):
            image.full_clean()

    def test_hex_swatches_reject_invalid_values(self):
        with self.assertRaises(ValidationError):
            DeviceColor(device=self.device, name="Silver", hex_code="navy").full_clean()
