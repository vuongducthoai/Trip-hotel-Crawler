"""Tests for international destinations catalog module."""
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import destinations


class DestinationsTests(unittest.TestCase):
    def test_catalog_structure(self):
        catalog_data = destinations.get_catalog()
        self.assertIn("countries", catalog_data)
        self.assertIn("catalog", catalog_data)
        self.assertEqual(len(catalog_data["countries"]), 19)
        self.assertNotIn("Vietnam", catalog_data["countries"])
        total_cities = sum(len(cities) for cities in catalog_data["catalog"].values())
        self.assertEqual(total_cities, 81)

    def test_find_by_city_id(self):
        bangkok = destinations.find_by_city_id(359)
        self.assertIsNotNone(bangkok)
        self.assertEqual(bangkok["city_name"], "Bangkok")
        self.assertEqual(bangkok["country_id"], 4)
        self.assertEqual(bangkok["country_name"], "Thailand")

        singapore = destinations.find_by_city_id(73)
        self.assertIsNotNone(singapore)
        self.assertEqual(singapore["city_name"], "Singapore")
        self.assertEqual(singapore["country_id"], 3)
        self.assertEqual(singapore["country_name"], "Singapore")

        # Vietnam cities are excluded from preset catalog
        self.assertIsNone(destinations.find_by_city_id(301))
        self.assertIsNone(destinations.find_by_city_id(9999999))

    def test_find_country_name(self):
        self.assertEqual(destinations.find_country_name(4), "Thailand")
        self.assertEqual(destinations.find_country_name(3), "Singapore")
        self.assertEqual(destinations.find_country_name(99999), "Quốc gia 99999")

    def test_all_cities(self):
        cities = destinations.all_cities()
        self.assertEqual(len(cities), 81)
        self.assertTrue(all("id" in c and "name" in c and "country_id" in c for c in cities))


if __name__ == "__main__":
    unittest.main()
