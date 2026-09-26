"""Integration tests for destinations API and parse_trip_url in server.py."""
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import destinations
from server import parse_trip_url


class ServerDestinationsTests(unittest.TestCase):
    def test_parse_trip_url_with_catalog_city(self):
        url = "https://vn.trip.com/hotels/list?cityId=359"
        place = parse_trip_url(url)
        self.assertEqual(place["city_id"], 359)
        self.assertEqual(place["city_name"], "Bangkok")
        self.assertEqual(place["country_id"], 4)
        self.assertEqual(place["country_name"], "Thailand")

    def test_parse_trip_url_with_unlisted_city(self):
        # Unlisted city (e.g. Vietnam or outside catalog) parsed cleanly via URL parameters
        url = "https://vn.trip.com/hotels/list?cityId=301&cityName=Ho%20Chi%20Minh%20City&countryId=111"
        place = parse_trip_url(url)
        self.assertEqual(place["city_id"], 301)
        self.assertIn("Ho Chi Minh", place["city_name"])
        self.assertEqual(place["country_id"], 111)


if __name__ == "__main__":
    unittest.main()
