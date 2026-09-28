"""Tests for international destinations catalog module."""
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import destinations


class DestinationsTests(unittest.TestCase):
    def setUp(self):
        destinations._load()

    def test_catalog_structure(self):
        catalog_data = destinations.get_catalog()
        self.assertIn("countries", catalog_data)
        self.assertIn("catalog", catalog_data)
        self.assertIn("country_tags", catalog_data)
        self.assertEqual(len(catalog_data["countries"]), 151)
        self.assertNotIn("Vietnam", catalog_data["countries"])
        total_cities = sum(len(cities) for cities in catalog_data["catalog"].values())
        self.assertEqual(total_cities, 1050)

    def test_priority_sorting_countries(self):
        catalog_data = destinations.get_catalog()
        countries = catalog_data["countries"]
        country_tags = catalog_data["country_tags"]
        # Tagged countries must come before untagged countries
        first_untagged_idx = None
        for i, c in enumerate(countries):
            tags = country_tags.get(c, [])
            if not tags:
                first_untagged_idx = i
                break
        self.assertIsNotNone(first_untagged_idx)
        self.assertEqual(first_untagged_idx, 20)  # All 20 tagged countries come first
        # Verify subsequent countries have no tags
        for c in countries[first_untagged_idx:]:
            self.assertEqual(country_tags.get(c, []), [])

    def test_priority_sorting_cities(self):
        catalog_data = destinations.get_catalog()
        # For Thailand: Bangkok has tags, should be first
        thailand_cities = catalog_data["catalog"]["Thailand"]
        self.assertTrue(len(thailand_cities) > 0)
        self.assertEqual(thailand_cities[0]["city_name"], "Bangkok")
        self.assertIn("#Vinfast", thailand_cities[0].get("tags", []))

    def test_find_by_city_id(self):
        bangkok = destinations.find_by_city_id(359)
        self.assertIsNotNone(bangkok)
        self.assertEqual(bangkok["city_name"], "Bangkok")
        self.assertEqual(bangkok["country_name"], "Thailand")
        self.assertIn("#Vinfast", bangkok.get("tags", []))

        singapore = destinations.find_by_city_id(73)
        self.assertIsNotNone(singapore)
        self.assertEqual(singapore["city_name"], "Singapore")
        self.assertEqual(singapore["country_name"], "Singapore")
        self.assertIn("#Vinfast", singapore.get("tags", []))

        # Vietnam cities are excluded from preset catalog
        self.assertIsNone(destinations.find_by_city_id(301))
        self.assertIsNone(destinations.find_by_city_id(9999999))

    def test_find_country_name(self):
        self.assertEqual(destinations.find_country_name(4), "Thailand")
        self.assertEqual(destinations.find_country_name(3), "Singapore")
        self.assertEqual(destinations.find_country_name(99999), "Quốc gia 99999")

    def test_all_cities(self):
        cities = destinations.all_cities()
        self.assertEqual(len(cities), 1050)
        self.assertTrue(all("id" in c and "name" in c and "country_id" in c for c in cities))


if __name__ == "__main__":
    unittest.main()
