import unittest
import tempfile
from pathlib import Path

import server
from server import csv_path, parse_trip_url


class ParseTripUrlTests(unittest.TestCase):
    def test_parse_full_trip_url(self):
        result = parse_trip_url(
            "https://vn.trip.com/hotels/list?cityId=301&countryId=111&cityName=Ho%20Chi%20Minh%20City"
        )
        self.assertEqual(result["city_id"], 301)
        self.assertEqual(result["country_id"], 111)
        self.assertEqual(result["city_name"], "Ho Chi Minh City")

    def test_parse_short_known_city_url(self):
        result = parse_trip_url("https://vn.trip.com/hotels/list?city=286")
        self.assertEqual(result["city_id"], 286)
        self.assertEqual(result["city_name"], "Hà Nội")

    def test_parse_hong_kong_url(self):
        result = parse_trip_url(
            "https://vn.trip.com/hotels/list?cityId=58&provinceId=32&countryId=1&cityName=H%E1%BB%93ng%20K%C3%B4ng"
        )
        self.assertEqual(result["city_id"], 58)
        self.assertEqual(result["province_id"], 32)
        self.assertEqual(result["country_id"], 1)
        self.assertEqual(result["country_name"], "Trung Quốc")

    def test_reject_lookalike_domain(self):
        with self.assertRaises(ValueError):
            parse_trip_url("https://nottrip.com/hotels/list?city=286")

    def test_reject_csv_path_traversal(self):
        with self.assertRaises(ValueError):
            csv_path("../du-lieu.csv")

    def test_trang_thai_da_tai_duoc_luu(self):
        old_path = server.DOWNLOAD_STATE_PATH
        try:
            with tempfile.TemporaryDirectory() as folder:
                server.DOWNLOAD_STATE_PATH = Path(folder) / "tai_csv.json"
                server.mark_downloaded("ket-qua.csv")
                self.assertIn("ket-qua.csv", server.download_state())
        finally:
            server.DOWNLOAD_STATE_PATH = old_path


if __name__ == "__main__":
    unittest.main()
