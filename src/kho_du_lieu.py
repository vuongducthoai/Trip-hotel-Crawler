"""Kho dữ liệu: đọc raw đã cào → danh sách, chi tiết và quét thiếu.

Không cần PostgreSQL. Mỗi khách sạn/thị trường lấy file raw MỚI NHẤT (giống
xuat_csv.doc_raw). Kết quả bóc được cache theo mtime để UI gọi lặp lại không
phải giải nén lại toàn bộ raw.
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config                       # noqa: E402
import raw_store                    # noqa: E402
import thay_doi                     # noqa: E402
from crawl_fast import detail_url, raw_city_info, raw_complete  # noqa: E402
from v2.extract import build_bundle  # noqa: E402

MARKETS = {"vi": ("vi-VN", "VND"), "en": ("en-US", "USD")}
_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict]] = {}   # raw path -> (mtime, tóm tắt)


def raw_root() -> Path:
    return config.OUTPUT_DIR / "details" / "raw"


def _newest_raws() -> dict[tuple[str, str], Path]:
    """(hotel_id, lang) → đường dẫn raw mới nhất, bỏ file .failed."""
    return {key: path for key, (path, _) in _newest_raws_with_mtime().items()}


def _newest_raws_with_mtime() -> dict[tuple[str, str], tuple[Path, float]]:
    newest: dict[tuple[str, str], tuple[float, Path]] = {}
    for lang, (locale, currency) in MARKETS.items():
        folder = raw_root() / locale / currency
        if not folder.exists():
            continue
        for path in folder.glob("*.json*"):
            if ".failed." in path.name or not path.is_file():
                continue
            hid = raw_store.hotel_id(path)
            if not hid.isdigit():
                continue
            mtime = path.stat().st_mtime
            key = (hid, lang)
            if key not in newest or mtime > newest[key][0]:
                newest[key] = (mtime, path)
    return {key: (path, mtime) for key, (mtime, path) in newest.items()}


def _summarize(path: Path, hid: str, lang: str, mtime: float | None = None) -> dict:
    """Bóc một raw thành tóm tắt nhẹ (không giữ mô tả/chính sách đầy đủ)."""
    locale, currency = MARKETS[lang]
    if mtime is None:
        mtime = path.stat().st_mtime
    cached = _CACHE.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    summary: dict[str, Any] = {
        "lang": lang, "raw_path": str(path), "raw_mtime": mtime,
        "cap_nhat": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
        "doc_duoc": False, "hoan_chinh": False,
        "ten": None, "dia_chi": None, "co_mo_ta": False,
        "so_chinh_sach": 0, "so_lan_can": 0, "city": None,
    }
    try:
        dump = raw_store.read(path)
    except (OSError, ValueError):
        _CACHE[str(path)] = (mtime, summary)
        return summary
    summary["hoan_chinh"] = raw_complete(dump)
    summary["city"] = raw_city_info(dump)
    try:
        bundle, _ = build_bundle(dump, raw_locale=locale, currency=currency,
                                 raw_path=str(path), file_hotel_id=hid)
    except Exception:
        bundle = None
    if bundle is not None and bundle.hotel_i18n is not None:
        i18n = bundle.hotel_i18n
        summary.update({
            "doc_duoc": True,
            "ten": i18n.name, "dia_chi": i18n.address,
            "co_mo_ta": bool((i18n.description or "").strip()),
            "so_chinh_sach": len(bundle.policy_sections),
            "so_lan_can": len(bundle.nearby),
        })
    _CACHE[str(path)] = (mtime, summary)
    return summary


def _flags(item: dict) -> list[str]:
    """Các mã thiếu của một khách sạn (gộp cả hai ngôn ngữ)."""
    flags: list[str] = []
    for lang in ("vi", "en"):
        ban = item["ngon_ngu"].get(lang)
        if ban is None:
            continue  # chưa cào ngôn ngữ này — không tính là thiếu, chỉ là chưa chọn
        if not ban["doc_duoc"]:
            flags.append(f"loi_{lang}")
            continue
        # Raw đã đủ packet (trang chi tiết + API lân cận) mà vẫn trống → Trip.com
        # không cung cấp phần đó cho khách sạn này: cờ "khong_*" (không phải lỗi cào).
        # Raw chưa đủ packet mà trống → có thể cào thiếu: cờ "mo_ta_*"… (cần cào bù).
        prefix = "khong_" if ban["hoan_chinh"] else ""
        if not ban["co_mo_ta"]:
            flags.append(f"{prefix}mo_ta_{lang}")
        if not ban["so_chinh_sach"]:
            flags.append(f"{prefix}chinh_sach_{lang}")
        if not ban["so_lan_can"]:
            flags.append(f"{prefix}lan_can_{lang}")
        if not ban["hoan_chinh"]:
            flags.append(f"chua_du_{lang}")
    if ("vi" in item["ngon_ngu"]) != ("en" in item["ngon_ngu"]):
        flags.append("thieu_ngon_ngu")
    return flags


def chat_luong(items: list[dict], city_ids: set[int] | None = None,
               ids: set[str] | None = None, chi_moi: bool = False) -> dict:
    """Báo cáo chất lượng cho một phạm vi: thiếu gì, bao nhiêu, ID nào cần cào bù.

    chi_moi=True → chỉ tính khách sạn chưa xuất CSV (mới từ lần xuất trước).
    """
    scope_all = [it for it in items
                 if (city_ids is None or it["city_id"] in city_ids)
                 and (ids is None or it["trip_hotel_id"] in ids)]
    if chi_moi:
        moi = set(chua_xuat_ids(scope_all))
        scope = [it for it in scope_all if it["trip_hotel_id"] in moi]
    else:
        scope = scope_all
    dem = {"mo_ta": 0, "chinh_sach": 0, "lan_can": 0, "chua_du": 0, "loi": 0, "thieu_ngon_ngu": 0}
    khong = {"mo_ta": 0, "chinh_sach": 0, "lan_can": 0}   # Trip.com không có phần này
    can_cao_bu: dict[str, set[str]] = {"vi": set(), "en": set()}
    thay_doi_ids: set[str] = set()
    for it in scope:
        flags = it["thieu"]
        for key in dem:
            if any(f == key or f.startswith(f"{key}_") for f in flags):
                dem[key] += 1
        for key in khong:
            if any(f.startswith(f"khong_{key}_") for f in flags):
                khong[key] += 1
        for lang in ("vi", "en"):
            # Chỉ cào bù khi thiếu do cào (không tính cờ khong_*).
            if any(f.endswith(f"_{lang}") and not f.startswith("khong_") for f in flags):
                can_cao_bu[lang].add(it["trip_hotel_id"])
            ban = it["ngon_ngu"].get(lang)
            if ban and ban.get("thay_doi"):
                thay_doi_ids.add(it["trip_hotel_id"])
    ids_bu = sorted(can_cao_bu["vi"] | can_cao_bu["en"])
    chua_xuat = len(chua_xuat_ids(scope_all))
    # Số khách sạn chưa xuất theo từng thành phố (toàn kho) để chip thành phố hiện "x mới / tổng".
    moi_all = set(chua_xuat_ids(items))
    theo_tp: dict[int, int] = {}
    for it in items:
        if it["city_id"] is not None and it["trip_hotel_id"] in moi_all:
            theo_tp[it["city_id"]] = theo_tp.get(it["city_id"], 0) + 1
    # "Thiếu do cào" = có cờ không phải khong_* (Trip.com không có) và không phải
    # thieu_ngon_ngu (người dùng chỉ chọn 1 ngôn ngữ).
    thieu_that = sum(1 for it in scope
                     if any(not f.startswith("khong_") and f != "thieu_ngon_ngu" for f in it["thieu"]))
    return {
        "tong": len(scope),
        "tong_pham_vi": len(scope_all),
        "chi_moi": chi_moi,
        "thieu": thieu_that,
        "khong_co": khong,
        "dem": dem,
        "cao_bu": {"ids": ids_bu, "vi": len(can_cao_bu["vi"]), "en": len(can_cao_bu["en"])},
        "thay_doi": len(thay_doi_ids),
        "chua_xuat": chua_xuat,
        "chua_xuat_theo_thanh_pho": theo_tp,
        "du": len(scope) - thieu_that,
    }


_LIST_MEMO: dict[str, Any] = {"at": 0.0, "value": None}
LIST_MEMO_SECONDS = 2.0


def danh_sach() -> list[dict]:
    """Toàn bộ khách sạn trong kho, mỗi khách sạn một dòng, gộp VI/EN."""
    import time
    with _LOCK:
        if _LIST_MEMO["value"] is not None and time.time() - _LIST_MEMO["at"] < LIST_MEMO_SECONDS:
            return _LIST_MEMO["value"]
        changes = {lang: thay_doi.doc_tat_ca(*MARKETS[lang]) for lang in MARKETS}
        hotels: dict[str, dict] = {}
        for (hid, lang), (path, mtime) in _newest_raws_with_mtime().items():
            s = _summarize(path, hid, lang, mtime)
            item = hotels.setdefault(hid, {
                "trip_hotel_id": hid, "ten": None, "ten_vi": None, "ten_en": None,
                "city_id": None, "city_name": None, "country_name": None,
                "ngon_ngu": {}, "cap_nhat": None,
            })
            item["ngon_ngu"][lang] = {
                k: s[k] for k in ("doc_duoc", "hoan_chinh", "co_mo_ta",
                                  "so_chinh_sach", "so_lan_can", "cap_nhat", "raw_path", "raw_mtime")
            }
            item["ngon_ngu"][lang]["thay_doi"] = changes[lang].get(hid)
            item[f"ten_{lang}"] = s["ten"]
            if s["city"] and not item["city_id"]:
                item["city_id"] = s["city"]["city_id"]
                item["city_name"] = s["city"]["city_name"]
                item["country_name"] = s["city"].get("country_name") or ""
            if not item["cap_nhat"] or s["cap_nhat"] > item["cap_nhat"]:
                item["cap_nhat"] = s["cap_nhat"]
        result = []
        for item in hotels.values():
            item["ten"] = item["ten_vi"] or item["ten_en"] or f"Khách sạn {item['trip_hotel_id']}"
            item["thieu"] = _flags(item)
            result.append(item)
        result.sort(key=lambda x: (x["cap_nhat"] or ""), reverse=True)
        _LIST_MEMO.update(at=time.time(), value=result)
        return result


# ---- Trạng thái đã xuất CSV: hotel_id → {lang: raw_mtime lúc xuất} ----
EXPORT_STATE_PATH = config.OUTPUT_DIR / "trang_thai_xuat_csv.json"
_EXPORT_LOCK = threading.Lock()


def _doc_trang_thai_xuat() -> dict:
    try:
        value = json.loads(EXPORT_STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def da_xuat(item: dict, state: dict | None = None) -> bool:
    """Khách sạn đã nằm trong CSV nào đó với raw hiện tại (mọi ngôn ngữ đang có)."""
    state = _doc_trang_thai_xuat() if state is None else state
    rec = state.get(item["trip_hotel_id"]) or {}
    for lang, ban in item["ngon_ngu"].items():
        if ban.get("raw_mtime") is None:
            continue
        if rec.get(lang) is None or ban["raw_mtime"] > rec[lang] + 1:
            return False
    return True


def chua_xuat_ids(items: list[dict]) -> list[str]:
    state = _doc_trang_thai_xuat()
    return [it["trip_hotel_id"] for it in items if not da_xuat(it, state)]


def danh_dau_da_xuat(ids: list[str]) -> None:
    """Ghi nhận các khách sạn vừa được xuất (theo raw_mtime hiện tại của từng ngôn ngữ)."""
    by_id = {it["trip_hotel_id"]: it for it in danh_sach()}
    with _EXPORT_LOCK:
        state = _doc_trang_thai_xuat()
        for hid in ids:
            it = by_id.get(hid)
            if not it:
                continue
            rec = state.setdefault(hid, {})
            for lang, ban in it["ngon_ngu"].items():
                if ban.get("raw_mtime") is not None:
                    rec[lang] = ban["raw_mtime"]
        EXPORT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = EXPORT_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(EXPORT_STATE_PATH)


def thong_ke(items: list[dict]) -> dict:
    cities: dict[int, dict] = {}
    for item in items:
        if item["city_id"] is None:
            continue
        c = cities.setdefault(item["city_id"], {
            "city_id": item["city_id"], "city_name": item["city_name"],
            "country_name": item["country_name"], "so_khach_san": 0,
        })
        c["so_khach_san"] += 1
    thieu = sum(1 for item in items
                if any(not f.startswith("khong_") and f != "thieu_ngon_ngu" for f in item["thieu"]))
    return {
        "tong": len(items), "thieu": thieu,
        "vi": sum(1 for item in items if "vi" in item["ngon_ngu"]),
        "en": sum(1 for item in items if "en" in item["ngon_ngu"]),
        "thanh_pho": sorted(cities.values(), key=lambda c: -c["so_khach_san"]),
    }


def chi_tiet(hotel_id: str, lang: str) -> dict:
    """Đầy đủ mô tả / chính sách / lân cận của một khách sạn ở một ngôn ngữ."""
    if lang not in MARKETS:
        raise ValueError("Ngôn ngữ không hợp lệ.")
    locale, currency = MARKETS[lang]
    path = _newest_raws().get((hotel_id, lang))
    if path is None:
        raise FileNotFoundError(f"Chưa có raw {lang} cho khách sạn {hotel_id}.")
    dump = raw_store.read(path)
    bundle, issues = build_bundle(dump, raw_locale=locale, currency=currency,
                                  raw_path=str(path), file_hotel_id=hotel_id)
    stat = path.stat()
    tomorrow = datetime.now() + timedelta(days=1)
    out: dict[str, Any] = {
        "trip_hotel_id": hotel_id, "lang": lang, "locale": locale, "currency": currency,
        "raw_path": str(path),
        "cap_nhat": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "hoan_chinh": raw_complete(dump),
        "city": raw_city_info(dump),
        "trip_url": detail_url(hotel_id, locale, currency,
                               tomorrow.strftime("%Y-%m-%d"),
                               (tomorrow + timedelta(days=1)).strftime("%Y-%m-%d")),
        "ten": None, "ten_dia_phuong": None, "dia_chi": None, "mo_ta": None,
        "so_phong": None, "chinh_sach": [], "lan_can": [],
        "thay_doi": thay_doi.doc(hotel_id, locale, currency),
        "loi_boc": [
            f"{getattr(i, 'severity', '')} {getattr(i, 'code', '')} · {getattr(i, 'entity', '')}"
            f"{(' · ' + str(i.field)) if getattr(i, 'field', None) else ''}"
            f"{(' · ' + str(i.detail)) if getattr(i, 'detail', None) else ''}".strip()
            for i in (getattr(issues, "items", None) or [])
        ][:30],
    }
    if bundle is None:
        return out
    if bundle.hotel is not None:
        out["so_phong"] = bundle.hotel.room_count
    if bundle.hotel_i18n is not None:
        i = bundle.hotel_i18n
        out.update({"ten": i.name, "ten_dia_phuong": i.local_name,
                    "dia_chi": i.address, "mo_ta": i.description})
    for s in sorted(bundle.policy_sections, key=lambda x: x.sort_order):
        out["chinh_sach"].append({
            "ma": s.section_code, "thu_tu": s.sort_order, "tieu_de": s.title,
            "dong": [{"nhan": label, "noi_dung": text, "dam": bool(bold)}
                     for label, text, bold in s.lines],
        })
    for n in sorted(bundle.nearby, key=lambda x: (x.group_code, x.sort_order or 0)):
        out["lan_can"].append({
            "poi_id": n.trip_poi_id, "ten": n.name, "loai": n.kind,
            "nhan_loai": n.type_label, "ma_nhom": n.group_code, "ten_nhom": n.group_name,
            "khoang_cach_km": float(n.distance_km) if n.distance_km is not None else None,
            "khoang_cach_chu": n.distance_text, "di_chuyen": n.travel_mode,
            "lat": n.latitude, "lng": n.longitude,
        })
    return out
