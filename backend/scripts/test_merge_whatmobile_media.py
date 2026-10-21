"""Regression checks: keep exact images, drop ambiguous identities safely."""
import csv
import tempfile
import unittest
from pathlib import Path

from merge_whatmobile_media import FIELDS, merge


def record(device, image, brand="Infinix", colors="Black, Green"):
    return {
        "brand": brand,
        "device": device,
        "source": "WhatMobile",
        "product_page": f"https://www.whatmobile.com.pk/{brand}_{device.replace(' ', '-')}",
        "image_url": f"https://www.whatmobile.com.pk/admin/images/{brand}/{image}.jpg",
        "colors": colors,
        "review_status": "USER_CONFIRMED_WHATMOBILE",
    }


class MergeWhatMobileTests(unittest.TestCase):
    def setup_shards(self, groups):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for i, group in enumerate(groups):
            with (root / f"whatmobile_media_{i}.csv").open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(group)
        return root

    def test_case_aliases_are_collapsed_only_when_same_image(self):
        root = self.setup_shards([
            [record("Hot 10S NFC", "InfinixHot10SNFC")],
            [record("Hot 10s NFC", "InfinixHot10SNFC")],
            [record("Hot 12", "InfinixHot12")],
        ])
        found = merge(root, root / "output.csv", min_photos=1)
        self.assertEqual(len(found), 2)
        self.assertEqual({x["device"].casefold() for x in found},
                         {"hot 10s nfc", "hot 12"})

    def test_shared_image_is_never_assigned_to_different_models(self):
        root = self.setup_shards([
            [record("X100s", "VivoX100s", brand="Vivo")],
            [record("X100s Pro", "VivoX100s", brand="Vivo")],
            [record("Hot 12", "InfinixHot12")],
        ])
        found = merge(root, root / "output.csv", min_photos=1)
        self.assertEqual([x["device"] for x in found], ["Hot 12"])

    def test_conflicting_alias_image_omits_both(self):
        root = self.setup_shards([
            [record("Note 11S", "InfinixNote11S")],
            [record("Note 11s", "InfinixNote11S_wrong")],
            [record("Hot 12", "InfinixHot12")],
        ])
        found = merge(root, root / "output.csv", min_photos=1)
        self.assertEqual([x["device"] for x in found], ["Hot 12"])

    def test_unapproved_host_fails_without_writing_csv(self):
        bad = record("Hot 12", "InfinixHot12")
        bad["image_url"] = "https://attacker.example/admin/images/fake.jpg"
        root = self.setup_shards([[bad], [], []])
        path = root / "output.csv"
        with self.assertRaisesRegex(ValueError, "Invalid publisher"):
            merge(root, path, min_photos=1)
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
