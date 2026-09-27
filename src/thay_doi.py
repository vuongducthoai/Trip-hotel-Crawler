"""So sánh raw mới với raw cũ của cùng khách sạn/thị trường, ghi lại phần khác nhau.

Ghi tại output/details/changes/<locale>/<currency>/<id>.json:
    {"hotel_id", "locale", "luc": ISO, "so_muc": n, "muc": [{"phan", "khoa", "truoc", "sau"}]}
Chỉ giữ lần so sánh gần nhất. Không có thay đổi → xoá file cũ (nếu có).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402

MAX_ITEMS = 60
SNIPPET = 160


def changes_dir(locale: str, currency: str) -> Path:
    return config.OUTPUT_DIR / "details" / "changes" / locale / currency.upper()


def change_path(hotel_id: str, locale: str, currency: str) -> Path:
    return changes_dir(locale, currency) / f"{hotel_id}.json"


def _fingerprint(dump: dict, locale: str, currency: str, hotel_id: str) -> dict | None:
    """Rút phần nội dung bàn giao (mô tả / chính sách / lân cận) ra dạng dễ so sánh."""
    from v2.extract import build_bundle
    try:
        bundle, _ = build_bundle(dump, raw_locale=locale, currency=currency,
                                 raw_path=None, file_hotel_id=hotel_id)
    except Exception:
        return None
    if bundle is None or bundle.hotel_i18n is None:
        return None
    i18n = bundle.hotel_i18n
    return {
        "thong_tin": {
            "Tên": i18n.name or "", "Địa chỉ": i18n.address or "",
            "Mô tả": (i18n.description or "").strip(),
        },
        "chinh_sach": {
            f"{s.title} ({s.section_code})": " | ".join(
                f"{(label or '').strip()}: {text.strip()}" if label else text.strip()
                for label, text, _ in s.lines)
            for s in bundle.policy_sections
        },
        "lan_can": {
            f"{n.group_name or n.group_code} · {n.name}": (
                f"{float(n.distance_km):.2f} km" if n.distance_km is not None else (n.distance_text or ""))
            for n in bundle.nearby
        },
    }


def _snip_pair(before: str, after: str) -> tuple[str, str]:
    """Trích đoạn quanh chỗ khác nhau đầu tiên, bỏ phần đầu giống nhau quá dài."""
    b = (before or "").replace("\n", " ").strip()
    a = (after or "").replace("\n", " ").strip()
    if len(b) <= SNIPPET and len(a) <= SNIPPET:
        return b, a
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    start = max(0, i - 40)
    # lùi về đầu từ cho dễ đọc
    while start > 0 and b[start - 1] not in " |":
        start -= 1
    prefix = "…" if start > 0 else ""

    def cut(v: str) -> str:
        part = v[start:start + SNIPPET]
        return prefix + part + ("…" if start + SNIPPET < len(v) else "")
    return cut(b), cut(a)


def so_sanh(old_dump: dict | None, new_dump: dict, hotel_id: str, locale: str, currency: str) -> dict | None:
    """Trả về bản ghi thay đổi, hoặc None nếu giống nhau / không so được."""
    if not old_dump:
        return None
    before = _fingerprint(old_dump, locale, currency, hotel_id)
    after = _fingerprint(new_dump, locale, currency, hotel_id)
    if before is None or after is None:
        return None
    items: list[dict] = []
    names = {"thong_tin": "Thông tin", "chinh_sach": "Chính sách", "lan_can": "Lân cận"}
    for phan in ("thong_tin", "chinh_sach", "lan_can"):
        b, a = before[phan], after[phan]
        for key in sorted(set(b) | set(a), key=str):
            if b.get(key, None) == a.get(key, None):
                continue
            kind = "them" if key not in b else "xoa" if key not in a else "sua"
            truoc, sau = _snip_pair(b.get(key, ""), a.get(key, ""))
            items.append({"phan": names[phan], "khoa": key, "loai": kind, "truoc": truoc, "sau": sau})
            if len(items) >= MAX_ITEMS:
                break
    if not items:
        return None
    tom_tat = {}
    for it in items:
        tom_tat[it["phan"]] = tom_tat.get(it["phan"], 0) + 1
    return {"hotel_id": hotel_id, "locale": locale, "currency": currency.upper(),
            "luc": datetime.now().isoformat(timespec="seconds"),
            "so_muc": len(items), "tom_tat": tom_tat, "muc": items}


def ghi(record: dict | None, hotel_id: str, locale: str, currency: str) -> None:
    path = change_path(hotel_id, locale, currency)
    if record is None:
        try:
            path.unlink()
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


def doc(hotel_id: str, locale: str, currency: str) -> dict | None:
    path = change_path(hotel_id, locale, currency)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def doc_tat_ca(locale: str, currency: str) -> dict[str, dict]:
    """hotel_id → tóm tắt thay đổi (không kèm chi tiết) cho toàn thị trường."""
    out: dict[str, dict] = {}
    folder = changes_dir(locale, currency)
    if not folder.exists():
        return out
    for path in folder.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[path.stem] = {"luc": rec.get("luc"), "so_muc": rec.get("so_muc", 0),
                          "tom_tat": rec.get("tom_tat", {})}
    return out
