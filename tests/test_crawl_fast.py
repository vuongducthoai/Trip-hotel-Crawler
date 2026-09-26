import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawl_fast import DETAIL_BLOCK_URL, NEARBY_URL, headers_for, raw_complete


class HeadersForTests(unittest.TestCase):
    def test_api_header_dung_market_va_trang_chi_tiet(self):
        referer = "https://vn.trip.com/hotels/detail/?hotelId=436519"
        headers = headers_for("vi-VN", "VND", referer=referer, json_api=True)

        self.assertEqual(headers["Accept"], "application/json")
        self.assertEqual(headers["Origin"], "https://vn.trip.com")
        self.assertEqual(headers["cookieorigin"], "https://vn.trip.com")
        self.assertEqual(headers["Referer"], referer)

    def test_raw_complete_can_ca_chi_tiet_va_surrounding(self):
        dump = {
            "normalized": {"success": True},
            "responses": [
                {"url": DETAIL_BLOCK_URL},
                {"url": f"https://vn.trip.com{NEARBY_URL}"},
            ],
        }
        self.assertTrue(raw_complete(dump))

    def test_raw_cu_thieu_surrounding_phai_cao_lai(self):
        dump = {
            "normalized": {"success": True},
            "responses": [{"url": DETAIL_BLOCK_URL}],
        }
        self.assertFalse(raw_complete(dump))


if __name__ == "__main__":
    unittest.main()
