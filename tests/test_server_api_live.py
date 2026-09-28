"""Direct HTTP tests against server handler logic."""
import json
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import destinations
import server


class LiveServerEndpointsTests(unittest.TestCase):
    def test_catalog_content_no_vietnam(self):
        cat = destinations.get_catalog()
        self.assertEqual(len(cat["countries"]), 151)
        self.assertNotIn("Vietnam", cat["countries"])
        # All countries have at least 1 city
        for country in cat["countries"]:
            cities = cat["catalog"].get(country, [])
            self.assertTrue(len(cities) > 0, f"Country {country} has no cities")
        total = sum(len(c) for c in cat["catalog"].values())
        self.assertEqual(total, 1050)

    def test_thailand_bangkok(self):
        item = destinations.find_by_city_id(359)
        self.assertIsNotNone(item)
        self.assertEqual(item["city_name"], "Bangkok")
        self.assertEqual(item["country_name"], "Thailand")

    def test_singapore(self):
        item = destinations.find_by_city_id(73)
        self.assertIsNotNone(item)
        self.assertEqual(item["city_name"], "Singapore")


if __name__ == "__main__":
    unittest.main()
