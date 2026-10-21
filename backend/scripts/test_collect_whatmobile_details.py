"""Check model-safe technical-spec and gallery parsing without network access."""
import unittest

from collect_whatmobile_details import (
    DetailParser, extract_specs, scalar_specs, gallery_urls,
)
from discover_retailer_phone_images import same_model

HTML = """
<title>Xiaomi 13 Pro Price and Specs</title>
<h1>Xiaomi 13 Pro</h1>
<table class="specs">
  <tr><th rowspan="3">Build</th><td>OS</td><td>Android 13 OS</td></tr>
  <tr><td>UI</td><td>MIUI 14</td></tr>
  <tr><td>Colors</td><td>Black, Blue, White, Mint</td></tr>
  <tr><th>Processor</th><td>Chipset</td><td>Qualcomm Snapdragon 8 Gen 2</td></tr>
  <tr><th>Display</th><td>Extra Features</td><td>120Hz, HDR10+</td></tr>
  <tr><th>Battery</th><td>Capacity</td><td>4820 mAh</td></tr>
  <tr><th>Camera</th><td>Main</td><td>50 MP + 50 MP + 50 MP</td></tr>
</table>
<table><tr><td>Price in Rs</td><td>214,999</td></tr></table>
<img src="/admin/images/Xiaomi/Xiaomi13Pro-b.jpg" alt="Xiaomi 13 Pro Mobile Price in Pakistan">
<a href="/admin/images/Xiaomi/Xiaomi13Pro-back.jpg" title="Xiaomi 13 Pro"></a>
<a href="/admin/images/Xiaomi/Xiaomi13Profront.jpg" title="Xiaomi 13 Pro"></a>
<a href="/admin/images/Xiaomi/Xiaomi13ProUltra-back.jpg" title="Xiaomi 13 Pro Ultra"></a>
"""


class DetailParserTests(unittest.TestCase):
    def test_scalars_and_sections_from_html_rows(self):
        page = DetailParser()
        page.feed(HTML)
        self.assertTrue(same_model(" ".join(page.h1).strip(), "Xiaomi", "13 Pro"))
        sections = extract_specs(page)
        self.assertEqual(sections["Build"]["OS"], "Android 13 OS")
        self.assertEqual(sections["Build"]["UI"], "MIUI 14")
        self.assertEqual(sections["Processor"]["Chipset"], "Qualcomm Snapdragon 8 Gen 2")
        self.assertEqual(sections["Camera"]["Main"], "50 MP + 50 MP + 50 MP")
        self.assertNotIn("Price in Rs", sections.get("Battery", {}))
        scalars = scalar_specs(sections)
        self.assertEqual(scalars["battery_mah"], 4820)
        self.assertEqual(scalars["refresh_hz"], 120)
        self.assertIn("Android 13", scalars["operating_system"])

    def test_no_other_phone_photo_or_unlinked_guess(self):
        page = DetailParser()
        page.feed(HTML)
        urls = gallery_urls(page, "https://www.whatmobile.com.pk/Xiaomi_13-Pro",
                            "Xiaomi", "13 Pro",
                            "https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi13Pro-b.jpg")
        self.assertIn("https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi13Pro-back.jpg",
                      urls)
        self.assertNotIn("https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi13ProUltra-back.jpg",
                         urls)
        self.assertNotIn("https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi13Profront.jpg",
                         urls)
        self.assertEqual(len(urls), 2)

    def test_wrong_header_rejected(self):
        self.assertFalse(same_model("Xiaomi 13 Pro Ultra", "Xiaomi", "13 Pro"))


if __name__ == "__main__":
    unittest.main()
