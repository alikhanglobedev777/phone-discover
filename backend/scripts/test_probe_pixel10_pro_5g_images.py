import csv
import tempfile
import unittest
from pathlib import Path

from probe_pixel10_pro_5g_images import scan


class Pixel10ProTests(unittest.TestCase):
    def test_only_actual_model_source_images_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "cat.csv"
            output = Path(directory) / "pics.csv"
            catalog.write_text("brand,device\nGoogle,Pixel 10 Pro\n", encoding="utf-8")
            accepted = {
                "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-10-pro-5g-1.jpg",
                "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-10-pro-5g-2.jpg",
            }
            rows = scan(catalog, output, validator=lambda url: url in accepted)
            self.assertEqual(set(rows), accepted)
            with output.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)


if __name__ == "__main__":
    unittest.main()
