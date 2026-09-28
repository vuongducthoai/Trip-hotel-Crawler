"""Ghép khách sạn Trip.com với Tripadvisor bằng Content API chính thức (không cào web).

Chuẩn hoá từ scripts/tripadvisor_match.py của project mẫu, bỏ phần PostgreSQL:
kết quả ghi thành output/tripadvisor/<trip_hotel_id>.json, mỗi khách sạn một file,
và được xuất CSV/SQL ở field ``tripAdvisorId`` (type DESCRIPTION / hotelInfo).

    python src/tripadvisor.py --ids 1234 5678          # vài khách sạn
    python src/tripadvisor.py --ids-file output/ids/x.txt
    python src/tripadvisor.py --tat-ca                  # mọi khách sạn trong kho chưa ghép
    python src/tripadvisor.py --tat-ca --lam-lai        # ghép lại cả khách sạn đã có kết quả

API key: ô "Tripadvisor API key" trong app (lưu output/tripadvisor/cai_dat.json)
hoặc biến môi trường TRIPADVISOR_API_KEY (.env).

Mỗi khách sạn mới: 1 lần Location Search (tên + toạ độ Trip.com) + 1 lần Location
Details → tối đa ~2 lần gọi. Hạn mức Tripadvisor ~10.000 lần/ngày.

Trạng thái ghép (giống project mẫu):
  matched  : tên giống ≥ 0.80 và cách nhau ≤ 300 m       → xuất tripAdvisorId
  review   : có ứng viên nhưng chưa chắc                → KHÔNG xuất, người xem lại
  no_match : Tripadvisor không có khách sạn phù hợp
  error    : gọi API lỗi → lần chạy sau sẽ thử lại
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config      # noqa: E402
import raw_store   # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.content.tripadvisor.com/api/v1"
MATCH_SIM, MATCH_DIST = 0.80, 300
REVIEW_SIM, REVIEW_DIST = 0.55, 1500
GENERIC = {"hotel", "hotels", "the", "by", "and", "a", "an", "resort", "inn", "suites", "suite",
           "apartments", "apartment", "hostel", "khach", "san", "spa", "collection", "&"}
TRANG_THAI_XUAT = {"matched"}          # chỉ trạng thái này mới được xuất tripAdvisorId
MARKETS = {"en": ("en-US", "USD"), "vi": ("vi-VN", "VND")}

THU_MUC = config.OUTPUT_DIR / "tripadvisor"
CAI_DAT_PATH = THU_MUC / "cai_dat.json"


class StopRun(Exception):
    """Hết hạn mức / sai key — dừng cả lượt chạy."""


# ------------------------------------------------------------------ cài đặt
def doc_cai_dat() -> dict:
    try:
        value = json.loads(CAI_DAT_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def ghi_cai_dat(**thay_doi) -> dict:
    cai_dat = {**doc_cai_dat(), **thay_doi}
    THU_MUC.mkdir(parents=True, exist_ok=True)
    tmp = CAI_DAT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cai_dat, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CAI_DAT_PATH)
    return cai_dat


def api_key() -> str:
    return (doc_cai_dat().get("api_key") or os.getenv("TRIPADVISOR_API_KEY") or "").strip()


def tu_dong_sau_crawl() -> bool:
    value = doc_cai_dat().get("tu_dong")
    return True if value is None else bool(value)


def che_key(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if len(key) > 10 else ("•" * len(key) if key else "")


# ------------------------------------------------------------------ kết quả
def ket_qua_path(hid: str) -> Path:
    return THU_MUC / f"{hid}.json"


def doc_ket_qua(hid: str) -> dict | None:
    try:
        value = json.loads(ket_qua_path(hid).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def ghi_ket_qua(hid: str, row: dict) -> None:
    THU_MUC.mkdir(parents=True, exist_ok=True)
    tmp = ket_qua_path(hid).with_suffix(".tmp")
    tmp.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ket_qua_path(hid))


def doc_tat_ca() -> dict[str, dict]:
    """trip_hotel_id → kết quả ghép (mọi trạng thái)."""
    ra: dict[str, dict] = {}
    if not THU_MUC.exists():
        return ra
    for path in THU_MUC.glob("*.json"):
        if path.stem.isdigit():
            row = doc_ket_qua(path.stem)
            if row:
                ra[path.stem] = row
    return ra


def tripadvisor_id(row: dict | None) -> str | None:
    """Giá trị cho field tripAdvisorId — chỉ khi ghép chắc chắn (matched)."""
    if not row or row.get("match_status") not in TRANG_THAI_XUAT:
        return None
    loc = row.get("tripadvisor_location_id")
    return str(loc) if loc else None


def thong_ke(ids: list[str] | None = None) -> dict:
    """Đếm trạng thái ghép cho danh sách khách sạn (None = mọi kết quả đã có)."""
    ket_qua = doc_tat_ca()
    dem = {"matched": 0, "review": 0, "no_match": 0, "error": 0, "chua_ghep": 0}
    for hid in (ids if ids is not None else list(ket_qua)):
        row = ket_qua.get(hid)
        if not row:
            dem["chua_ghep"] += 1
        else:
            dem[row.get("match_status") or "error"] = dem.get(row.get("match_status") or "error", 0) + 1
    dem["tong"] = len(ids) if ids is not None else len(ket_qua)
    dem["co_key"] = bool(api_key())
    dem["tu_dong"] = tu_dong_sau_crawl()
    return dem


def can_ghep(hid: str, lam_lai: bool = False) -> bool:
    row = doc_ket_qua(hid)
    if row is None or lam_lai:
        return True
    return row.get("match_status") == "error"


# ------------------------------------------------------------------ đọc raw
def thong_tin_khach_san(hid: str) -> dict | None:
    """Tên (ưu tiên EN) + toạ độ từ raw mới nhất, không cần DB."""
    from v2.extract import build_bundle
    ra: dict = {"trip_hotel_id": hid, "name": None, "latitude": None, "longitude": None}
    for lang, (locale, currency) in MARKETS.items():
        folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency
        candidates = [p for p in folder.glob(f"{hid}.json*") if ".failed." not in p.name] if folder.exists() else []
        if not candidates:
            continue
        path = max(candidates, key=lambda p: p.stat().st_mtime)
        try:
            b, _ = build_bundle(raw_store.read(path), raw_locale=locale, currency=currency,
                                raw_path=str(path), file_hotel_id=hid)
        except Exception:
            continue
        if b is None:
            continue
        if b.hotel_i18n and not ra["name"]:
            ra["name"] = b.hotel_i18n.name
            ra["lang"] = lang
        if b.hotel and ra["latitude"] is None and b.hotel.latitude is not None:
            ra["latitude"], ra["longitude"] = b.hotel.latitude, b.hotel.longitude
        if ra["name"] and ra["latitude"] is not None and lang == "en":
            break
    return ra if ra["name"] else None


def ids_trong_kho() -> list[str]:
    ids: set[str] = set()
    for locale, currency in MARKETS.values():
        folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency
        if folder.exists():
            for p in folder.glob("*.json*"):
                if ".failed." not in p.name:
                    hid = raw_store.hotel_id(p)
                    if hid.isdigit():
                        ids.add(hid)
    return sorted(ids)


# ------------------------------------------------------------------ so khớp
def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("ø", "o").replace("æ", "ae").replace("å", "a").replace("đ", "d")
    words = [w for w in re.findall(r"[a-z0-9]+", text) if w not in GENERIC]
    return " ".join(words)


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    wa, wb = set(na.split()), set(nb.split())
    overlap = len(wa & wb) / min(len(wa), len(wb))
    return round(max(ratio, overlap * 0.95), 3)


def distance_m(lat1, lng1, lat2, lng2) -> int | None:
    try:
        lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    except (TypeError, ValueError):
        return None
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(2 * r * math.asin(math.sqrt(a))))


def classify(similarity: float, distance: int | None) -> str:
    if distance is None:
        return "review" if similarity >= MATCH_SIM else "no_match"
    if similarity >= MATCH_SIM and distance <= MATCH_DIST:
        return "matched"
    if similarity >= REVIEW_SIM and distance <= REVIEW_DIST:
        return "review"
    return "no_match"


def parse_details(data: dict) -> dict:
    rating = review_count = None
    try:
        rating = float(data.get("rating")) if data.get("rating") not in (None, "") else None
    except (TypeError, ValueError):
        rating = None
    if rating is not None and not 0 <= rating <= 5:
        rating = None
    try:
        review_count = int(str(data.get("num_reviews") or "").replace(",", "")) \
            if data.get("num_reviews") not in (None, "") else None
    except ValueError:
        review_count = None
    url = data.get("web_url") or None
    if url and not re.match(r"^https://([a-z0-9-]+\.)*tripadvisor\.[a-z.]+/", url):
        url = None
    return {"rating": rating, "review_count": review_count, "tripadvisor_url": url,
            "tripadvisor_name": data.get("name"),
            "latitude": data.get("latitude"), "longitude": data.get("longitude")}


# ------------------------------------------------------------------ API
class Client:
    def __init__(self, key: str, max_calls: int = 9000, pause: float = 0.2,
                 radius_km: float = 5.0, http=None):
        import httpx
        self.key = key
        self.max_calls = max_calls
        self.pause = pause
        self.radius_km = radius_km
        self.calls = 0
        self.http = http or httpx.Client(timeout=20, headers={"accept": "application/json"})

    def get(self, path: str, **params) -> dict:
        if self.calls >= self.max_calls:
            raise StopRun(f"đã dùng hết giới hạn {self.max_calls} lần gọi cho lượt này")
        self.calls += 1
        response = self.http.get(f"{API}{path}", params={"key": self.key, "language": "en", **params})
        if response.status_code == 429:
            raise StopRun("Tripadvisor báo 429 — hết hạn mức ngày/tháng, chạy lại sau")
        if response.status_code in (401, 403):
            raise StopRun(f"Tripadvisor báo {response.status_code} — kiểm tra API key / IP được phép")
        response.raise_for_status()
        time.sleep(self.pause)
        return response.json()

    def search(self, name: str, lat, lng) -> list[dict]:
        params = {"searchQuery": name, "category": "hotels"}
        if lat is not None and lng is not None:
            params["latLong"] = f"{lat},{lng}"
            params["radius"] = self.radius_km
            params["radiusUnit"] = "km"
        return (self.get("/location/search", **params).get("data")) or []

    def details(self, location_id) -> dict:
        return self.get(f"/location/{location_id}/details", currency="USD")


def match_hotel(client: Client, hotel: dict) -> dict:
    row = {"trip_hotel_id": hotel["trip_hotel_id"], "trip_name": hotel["name"],
           "trip_lat": hotel.get("latitude"), "trip_lng": hotel.get("longitude"),
           "tripadvisor_location_id": None, "match_status": "no_match", "name_similarity": None,
           "distance_m": None, "tripadvisor_name": None, "rating": None, "review_count": None,
           "tripadvisor_url": None, "last_error": None,
           "searched_at": datetime.now().isoformat(timespec="seconds")}
    candidates = client.search(hotel["name"], hotel.get("latitude"), hotel.get("longitude"))
    if not candidates:
        return row
    best = max(candidates[:10], key=lambda c: name_similarity(hotel["name"], c.get("name", "")))
    similarity = name_similarity(hotel["name"], best.get("name", ""))
    if similarity < REVIEW_SIM:
        row.update(name_similarity=similarity, tripadvisor_name=best.get("name"))
        return row
    details = parse_details(client.details(best["location_id"]))
    distance = distance_m(hotel.get("latitude"), hotel.get("longitude"),
                          details["latitude"], details["longitude"])
    status = classify(similarity, distance)
    row.update(tripadvisor_location_id=int(best["location_id"]), match_status=status,
               name_similarity=similarity, distance_m=distance,
               tripadvisor_name=details["tripadvisor_name"] or best.get("name"),
               rating=details["rating"], review_count=details["review_count"],
               tripadvisor_url=details["tripadvisor_url"])
    if status == "no_match":
        row["tripadvisor_location_id"] = None
    return row


# ------------------------------------------------------------------ chạy
def ghep(ids: list[str], *, lam_lai: bool = False, max_calls: int = 9000, pause: float = 0.2,
         radius_km: float = 5.0, nhan: str = "TRIPADVISOR") -> dict:
    """Ghép các khách sạn; trả về số đếm theo trạng thái. Không ném lỗi ra ngoài.

    Dòng log không dùng dạng [n/N] để không làm lệch thanh tiến trình của job crawl.
    """
    dem = {"matched": 0, "review": 0, "no_match": 0, "error": 0, "bo_qua": 0, "khong_raw": 0, "goi": 0}
    key = api_key()
    if not key:
        print(f"{nhan} · bỏ qua: chưa có Tripadvisor API key (nhập ở tab File CSV).")
        dem["bo_qua"] = len(ids)
        return dem
    can = [hid for hid in ids if can_ghep(hid, lam_lai)]
    dem["bo_qua"] = len(ids) - len(can)
    print(f"{nhan} · {len(can)} khách sạn cần ghép ({dem['bo_qua']} đã có kết quả, bỏ qua) · key {che_key(key)}")
    if not can:
        return dem
    try:
        client = Client(key, max_calls, pause, radius_km)
    except ImportError as exc:
        print(f"{nhan} · lỗi: {exc}")
        dem["error"] = len(can)
        return dem
    try:
        for index, hid in enumerate(can, 1):
            hotel = thong_tin_khach_san(hid)
            if not hotel:
                dem["khong_raw"] += 1
                print(f"{nhan} {index}·{len(can)} · {hid} · không đọc được raw")
                continue
            try:
                row = match_hotel(client, hotel)
            except StopRun:
                raise
            except Exception as exc:
                row = {"trip_hotel_id": hid, "trip_name": hotel["name"], "match_status": "error",
                       "tripadvisor_location_id": None,
                       "last_error": f"{type(exc).__name__}: {exc}"[:300],
                       "searched_at": datetime.now().isoformat(timespec="seconds")}
            ghi_ket_qua(hid, row)
            dem[row["match_status"]] = dem.get(row["match_status"], 0) + 1
            extra = (f" → {row.get('tripadvisor_location_id')} ({row.get('tripadvisor_name')})"
                     if row.get("tripadvisor_location_id") else "")
            if row["match_status"] == "error":
                extra = f" · {row.get('last_error')}"
            print(f"{nhan} {index}·{len(can)} · {hid} {hotel['name'][:40]} · {row['match_status']}{extra}", flush=True)
    except StopRun as why:
        print(f"{nhan} · DỪNG: {why}")
        dem["dung"] = str(why)
    dem["goi"] = client.calls
    print(f"{nhan} · xong: {dem['matched']} matched · {dem['review']} review · {dem['no_match']} no_match"
          f" · {dem['error']} lỗi · {client.calls} lần gọi API")
    return dem


def ghep_sau_crawl(ids: list[str]) -> None:
    """Gọi ở cuối job crawl: chỉ chạy khi có key và bật tự động; không bao giờ làm hỏng job."""
    try:
        if not ids or not api_key() or not tu_dong_sau_crawl():
            return
        print("TRIPADVISOR · ghép tự động sau crawl")
        ghep([str(x) for x in ids])
    except Exception as exc:   # pragma: no cover - phòng hờ
        print(f"TRIPADVISOR · lỗi không mong đợi: {exc}")


def main(args) -> int:
    ids: list[str] = []
    if args.ids_file:
        ids += [x for x in re.split(r"\s+", Path(args.ids_file).read_text(encoding="utf-8").strip()) if x]
    if args.ids:
        ids += [str(x) for x in args.ids]
    if args.tat_ca:
        ids += ids_trong_kho()
    ids = list(dict.fromkeys(i for i in ids if str(i).isdigit()))
    if not ids:
        print("Không có khách sạn nào để ghép.")
        return 2
    if not api_key():
        print("Thiếu Tripadvisor API key: nhập trong app (tab File CSV) hoặc đặt TRIPADVISOR_API_KEY.")
        return 1
    print(f"GHÉP TRIPADVISOR · {len(ids)} khách sạn")
    dem = ghep(ids, lam_lai=args.lam_lai, max_calls=args.max_calls, pause=args.pause,
               radius_km=args.radius_km)
    if dem.get("dung"):
        return 2
    if dem["error"] and not (dem["matched"] or dem["review"] or dem["no_match"]):
        return 3   # mọi khách sạn đều lỗi (mạng, key…) → báo "chưa đủ" thay vì thành công
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ids", nargs="*", help="trip_hotel_id cần ghép")
    ap.add_argument("--ids-file", help="file chứa ID, mỗi dòng một ID")
    ap.add_argument("--tat-ca", action="store_true", help="mọi khách sạn có raw trong kho")
    ap.add_argument("--lam-lai", action="store_true", help="ghép lại cả khách sạn đã có kết quả")
    ap.add_argument("--max-calls", type=int, default=9000)
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--radius-km", type=float, default=5.0)
    sys.exit(main(ap.parse_args()))
