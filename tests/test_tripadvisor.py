"""Kiểm tra ghép Tripadvisor bằng HTTP giả — không gọi API thật."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tripadvisor as ta  # noqa: E402


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _Http:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/location/search"):
            return _Resp({"data": [
                {"location_id": "111", "name": "Random Hostel"},
                {"location_id": "222", "name": "Scandic Norreport Copenhagen"},
            ]})
        return _Resp({"name": "Scandic Norreport", "rating": "4.5", "num_reviews": "1,234",
                      "web_url": "https://www.tripadvisor.com/Hotel_Review-x.html",
                      "latitude": "55.6832", "longitude": "12.5710"})


def test_match_hotel_matched(tmp_path, monkeypatch):
    client = ta.Client("k", http=_Http(), pause=0)
    row = ta.match_hotel(client, {"trip_hotel_id": "1", "name": "Scandic Nørreport",
                                  "latitude": 55.6830, "longitude": 12.5712})
    assert row["match_status"] == "matched"
    assert row["tripadvisor_location_id"] == 222
    assert row["rating"] == 4.5 and row["review_count"] == 1234
    assert ta.tripadvisor_id(row) == "222"


def test_review_khong_xuat():
    client = ta.Client("k", http=_Http(), pause=0)
    row = ta.match_hotel(client, {"trip_hotel_id": "1", "name": "Scandic Nørreport",
                                  "latitude": 55.6900, "longitude": 12.5712})   # ~760 m
    assert row["match_status"] == "review"
    assert ta.tripadvisor_id(row) is None


def test_ghi_doc_ket_qua(tmp_path, monkeypatch):
    monkeypatch.setattr(ta, "THU_MUC", tmp_path)
    monkeypatch.setattr(ta, "CAI_DAT_PATH", tmp_path / "cai_dat.json")
    ta.ghi_ket_qua("5", {"trip_hotel_id": "5", "match_status": "matched", "tripadvisor_location_id": 9})
    assert ta.doc_tat_ca()["5"]["tripadvisor_location_id"] == 9
    assert ta.can_ghep("5") is False and ta.can_ghep("5", lam_lai=True) is True
    ta.ghi_ket_qua("6", {"trip_hotel_id": "6", "match_status": "error"})
    assert ta.can_ghep("6") is True
    tk = ta.thong_ke(["5", "6", "7"])
    assert tk["matched"] == 1 and tk["error"] == 1 and tk["chua_ghep"] == 1
    ta.ghi_cai_dat(api_key="abc")
    assert ta.api_key() == "abc"
