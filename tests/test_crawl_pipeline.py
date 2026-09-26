import json
import tempfile
import unittest
from pathlib import Path
from argparse import Namespace
from unittest.mock import AsyncMock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
import crawl_pipeline
from crawl_pipeline import combined_ids


class CombinedIdsTests(unittest.TestCase):
    @staticmethod
    def args():
        return Namespace(
            languages=["vi"], city_id=58, city_name="Hồng Kông",
            province_id=32, country_id=1, country_name="Trung Quốc",
            limit=2, continue_mode=True,
        )

    def test_gop_danh_sach_moi_va_checkpoint_cu_khong_trung(self):
        old_dir = config.DATA_DIR
        try:
            with tempfile.TemporaryDirectory() as folder:
                config.DATA_DIR = Path(folder)
                older = config.DATA_DIR / "api_hotels_58_viVN_VND_20260101_000000.json"
                current = config.DATA_DIR / "api_hotels_58_viVN_VND_20260102_000000.json"
                older.write_text(json.dumps({"hotels": [
                    {"trip_hotel_id": "2"}, {"trip_hotel_id": "3"},
                ]}), encoding="utf-8")
                current.write_text(json.dumps({"hotels": [
                    {"trip_hotel_id": "1"}, {"trip_hotel_id": "2"},
                ]}), encoding="utf-8")

                self.assertEqual(combined_ids(current, 58, "vi-VN", "VND", 10),
                                 ["1", "2", "3"])
        finally:
            config.DATA_DIR = old_dir

    def test_cao_tiep_khong_co_id_moi_tra_trang_thai_chua_du(self):
        old_dir = config.DATA_DIR
        try:
            with tempfile.TemporaryDirectory() as folder:
                config.DATA_DIR = Path(folder)
                source = config.DATA_DIR / "api_hotels_58_viVN_VND_20260102_000000.json"
                source.write_text(json.dumps({"hotels": [
                    {"trip_hotel_id": "1"}, {"trip_hotel_id": "2"},
                ]}), encoding="utf-8")
                with patch.object(crawl_pipeline.crawl_api, "main", new=AsyncMock()), \
                     patch.object(crawl_pipeline.crawl_fast, "complete_city_ids", return_value={"1", "2"}), \
                     patch.object(crawl_pipeline.crawl_fast, "main") as detail:
                    self.assertEqual(crawl_pipeline.main(self.args()), 3)
                    detail.assert_not_called()
        finally:
            config.DATA_DIR = old_dir

    def test_cao_tiep_chi_gui_id_con_thieu_vao_chi_tiet(self):
        old_dir = config.DATA_DIR
        try:
            with tempfile.TemporaryDirectory() as folder:
                config.DATA_DIR = Path(folder)
                source = config.DATA_DIR / "api_hotels_58_viVN_VND_20260102_000000.json"
                source.write_text(json.dumps({"hotels": [
                    {"trip_hotel_id": value} for value in ("1", "2", "3", "4")
                ]}), encoding="utf-8")
                with patch.object(crawl_pipeline.crawl_api, "main", new=AsyncMock()), \
                     patch.object(crawl_pipeline.crawl_fast, "complete_city_ids", return_value={"1", "2"}), \
                     patch.object(crawl_pipeline.crawl_fast, "main", return_value=0) as detail:
                    self.assertEqual(crawl_pipeline.main(self.args()), 0)
                    call_args = detail.call_args.args[0]
                    self.assertEqual(call_args.ids, ["3", "4"])
                    self.assertEqual(call_args.limit, 2)
        finally:
            config.DATA_DIR = old_dir


if __name__ == "__main__":
    unittest.main()
