"""Source-confirmed variants/colors: no fabricated options, colors or prices."""

from copy import deepcopy
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from catalog.models import Device, DeviceColor, DeviceVariant, MarketPriceObservation
from catalog.web_import import import_web_phones
from .phone_options import color_names, extract_memory_pairs, extract_source_options
from .source_research import research_urls


URL = "https://www.whatmobile.com.pk/Samsung_Galaxy-S26-Ultra"
HTML = """
<h1>Samsung Galaxy S26 Ultra</h1><div>Rs. 384,999</div>
<table>
<tr><th class="specs-subHeading">Built-in</th>
    <td class="specs-value">256GB Built-in, 12GB RAM</td></tr>
<tr><th class="specs-subHeading">Colors</th>
    <td class="specs-value">Titanium Gray, Titanium Black, Titanium Violet</td></tr>
</table>
"""


def preview():
    return {
        "provider": "tavily", "status": "grounded_preview",
        "sources": [{"url": URL}],
        "document": {"phones": [{
            "brand": "Samsung", "name": "Galaxy S26 Ultra",
            "ram_gb": 12, "storage_gb": 256, "source_url": URL,
            "price_min_pkr": "384999", "price_max_pkr": "384999",
            "condition": "box_pack", "pta_status": "unknown", "city": "",
            "_source_parsed_options": True,
            "available_variants": [
                {"ram_gb": 8, "storage_gb": 128}, {"ram_gb": 8, "storage_gb": 256},
                {"ram_gb": 12, "storage_gb": 128}, {"ram_gb": 12, "storage_gb": 256},
                {"ram_gb": 12, "storage_gb": 512}, {"ram_gb": 12, "storage_gb": 1024},
            ],
            "available_colors": ["Titanium Gray", "Titanium Black", "Titanium Violet"],
        }]},
    }


class SourceOptionParsingTests(SimpleTestCase):
    def test_explicit_pairs_include_1tb_without_cross_product(self):
        cases = (
            "8GB RAM / 128GB storage, 8GB RAM / 256GB storage, "
            "12GB RAM / 128GB storage, 12GB RAM / 256GB storage, "
            "12GB RAM / 512GB storage, 12GB RAM / 1TB storage"
        )
        self.assertEqual(set(extract_memory_pairs(cases)), {
            (8, 128), (8, 256), (12, 128), (12, 256), (12, 512), (12, 1024)
        })
        self.assertEqual(extract_memory_pairs("8/12GB RAM, 128/256GB storage"), [])

    def test_whatmobile_labeled_colors_and_variant(self):
        options = extract_source_options(HTML, URL, "Samsung", "Galaxy S26 Ultra")
        self.assertEqual(options["variants"], [{"ram_gb": 12, "storage_gb": 256}])
        self.assertEqual(options["colors"], ["Titanium Gray", "Titanium Black", "Titanium Violet"])
        self.assertEqual(extract_source_options(HTML, URL, "Samsung", "Galaxy S26 Plus"),
                         {"variants": [], "colors": []})

    def test_labeled_retailer_color_selector(self):
        url = "https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb/"
        html = ('<h1>Samsung Galaxy S26 Ultra 12GB 256GB</h1>'
                '<select name="attribute_pa_color"><option>Choose a color</option>'
                '<option>Titanium Black</option><option>Titanium Silver</option></select>')
        options = extract_source_options(html, url, "Samsung", "Galaxy S26 Ultra")
        self.assertEqual(options["variants"], [{"ram_gb": 12, "storage_gb": 256}])
        self.assertEqual(options["colors"], ["Titanium Black", "Titanium Silver"])

    def test_reject_invented_finish_lists(self):
        self.assertEqual(color_names("Choose color, Assorted, 16 Million colors"), [])

    def test_product_group_variants_have_explicit_pairs(self):
        url = "https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb/"
        html = ('''<h1>Samsung Galaxy S26 Ultra 12GB 256GB</h1>
        <script type="application/ld+json">{
          "@type": "ProductGroup", "name": "Samsung Galaxy S26 Ultra",
          "hasVariant": [
            {"@type": "Product", "name": "Samsung Galaxy S26 Ultra 12GB 512GB"},
            {"@type": "Product", "name": "Samsung Galaxy S26 Ultra 12GB 1TB"},
            {"@type": "Product", "name": "Samsung Galaxy S26 Plus 8GB 128GB"}
          ]
        }</script>''')
        options = extract_source_options(html, url, "Samsung", "Galaxy S26 Ultra")
        self.assertEqual({(x["ram_gb"], x["storage_gb"]) for x in options["variants"]},
                         {(12, 256), (12, 512), (12, 1024)})

    @patch("recommendations.source_research._fetch", return_value=HTML)
    def test_researched_phone_receives_page_parsed_options(self, fetch):
        found = research_urls({"brand": "samsung", "device_query": "Galaxy S26 Ultra"},
                              [{"url": URL}], provider="tavily")
        self.assertEqual(found["status"], "grounded_preview")
        phone = found["document"]["phones"][0]
        self.assertIs(phone["_source_parsed_options"], True)
        self.assertEqual(phone["available_colors"][0], "Titanium Gray")


class OptionImportTests(TestCase):
    def test_each_documented_variant_unpriced_except_cited_sale(self):
        stats, slugs = import_web_phones(preview())
        self.assertEqual(stats["devices_created"], 1)
        self.assertEqual(stats["variants_created"], 6)
        self.assertEqual(stats["colors_created"], 3)
        self.assertEqual(DeviceVariant.objects.count(), 6)
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        self.assertEqual((MarketPriceObservation.objects.get().variant.ram_gb,
                          MarketPriceObservation.objects.get().variant.storage_gb), (12, 256))
        device = Device.objects.get(slug=slugs[0])
        self.assertEqual(device.colors.count(), 3)
        self.assertEqual(device.specifications["_web_option_sources"], [URL])

    def test_reimport_is_idempotent_and_keeps_manual_swatches(self):
        import_web_phones(preview())
        custom = DeviceColor.objects.get(name="Titanium Black")
        custom.hex_code = "#010101"
        custom.save(update_fields=["hex_code"])
        stats, _ = import_web_phones(preview())
        self.assertEqual(stats["variants_created"], 0)
        self.assertEqual(stats["colors_created"], 0)
        self.assertEqual(DeviceColor.objects.get(name="Titanium Black").hex_code, "#010101")
        self.assertEqual(MarketPriceObservation.objects.count(), 1)

    def test_model_generated_options_are_not_imported(self):
        research = deepcopy(preview())
        research["provider"] = "gemini"
        stats, _ = import_web_phones(research)
        # The one priced configuration is always created, but model-written
        # extra variants and colors must not be imported.
        self.assertEqual(stats["variants_created"], 1)
        self.assertEqual(stats["colors_created"], 0)
        self.assertEqual(DeviceVariant.objects.count(), 1)
        self.assertTrue(DeviceVariant.objects.filter(ram_gb=12, storage_gb=256).exists())

    def test_no_untrusted_marker_means_only_price_variant(self):
        research = deepcopy(preview())
        del research["document"]["phones"][0]["_source_parsed_options"]
        stats, _ = import_web_phones(research)
        # Without the source-parser marker, only the actual priced SKU is
        # imported; none of the claimed extra configurations are trusted.
        self.assertEqual(stats["variants_created"], 1)
        self.assertEqual(stats["colors_created"], 0)
        self.assertEqual(DeviceVariant.objects.count(), 1)
        self.assertTrue(DeviceVariant.objects.filter(ram_gb=12, storage_gb=256).exists())

    def test_source_variants_cannot_take_other_variants_prices(self):
        import_web_phones(preview())
        self.assertFalse(DeviceVariant.objects.get(ram_gb=8, storage_gb=128).pk_market_prices.exists())
