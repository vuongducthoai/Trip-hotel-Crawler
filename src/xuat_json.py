"""Xuất JSON gom theo khách sạn — cùng dữ liệu với CSV/SQL, chỉ khác cách sắp xếp.

Dùng chung doc_raw()/sinh_dong() với xuat_csv.py nên JSON luôn khớp CSV/SQL
(cùng row_uuid, cùng HTML mô tả/chính sách, cùng field tripAdvisorId).

    python src/xuat_json.py --ra output/csv/x.json              # tất cả raw
    python src/xuat_json.py --ids 989485 13385490 --ra x.json  # vài khách sạn
    python src/xuat_json.py --tach-file --ra output/json_mentor  # mỗi khách sạn một file

Cấu trúc một khách sạn (giống file đã gửi mentor):
{
  "property_id": 989485, "hotel_name": "...", "source_table": "...",
  "DESCRIPTION": {"row_uuid", "section_type": "hotelInfo", "row_key", "vi": {field: value}, "en": {...}},
  "POLICY":      [{"section_type", "row_uuid", "row_key", "vi": {policy_title, policy_content}, "en": {...}}],
  "SURROUNDING": [{"group_code": "02", "section_type": {"vi": "02_Giao thông", "en": "02_Transport"},
                   "places": [{"row_uuid", "row_key", "vi": {...}, "en": {...}}]}]
}
row_uuid = md5(row_key)::uuid; row_key = "<property_id>:DESCRIPTION" |
"<property_id>:POLICY:<section_type>" | "<property_id>:SURROUNDING:<trip_poi_id>".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xuat_csv import CAC_COT, doc_raw, sinh_dong  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BANG = "splatform_meta.trip_tmp_property_translation"


def gom(ks: dict) -> list[dict]:
    """Biến các dòng 7 cột thành danh sách khách sạn gom theo type."""
    dong = [d for d in sinh_dong(ks) if d[8] is not None and str(d[8]).strip() != ""]
    dong.sort(key=lambda d: (d[0], d[1], d[2], d[3]))
    # poi_id của SURROUNDING không nằm trong 7 cột → lấy lại từ raw để ghi row_key
    poi_cua: dict[tuple[int, str], int] = {}
    for hid, muc in ks.items():
        for ban in muc.ban.values():
            for p in ban.nearby:
                poi_cua[(int(hid), f"{hid}:SURROUNDING:{p.trip_poi_id}")] = p.trip_poi_id
    poi_theo_uuid: dict[str, int] = {}
    from xuat_csv import ma_uuid
    for (pid, khoa), poi in poi_cua.items():
        poi_theo_uuid[ma_uuid(khoa)] = poi

    ra: dict[int, dict] = {}
    for pid, lang, _ord, _sub, uid, loai, section, ten, gt in dong:
        h = ra.setdefault(pid, {
            "property_id": pid, "hotel_name": None, "source_table": BANG,
            "DESCRIPTION": {"row_uuid": None, "section_type": "hotelInfo", "row_key": f"{pid}:DESCRIPTION"},
            "_policy": {}, "_sur": {},
        })
        if loai == "DESCRIPTION":
            h["DESCRIPTION"]["row_uuid"] = uid
            h["DESCRIPTION"].setdefault(lang, {})[ten] = gt
            if ten == "hotel_name" and (lang == "en" or not h["hotel_name"]):
                h["hotel_name"] = gt
        elif loai == "POLICY":
            s = h["_policy"].setdefault(section, {"section_type": section, "row_uuid": uid,
                                                  "row_key": f"{pid}:POLICY:{section}"})
            s.setdefault(lang, {})[ten] = gt
        else:
            code = section.partition("_")[0]
            g = h["_sur"].setdefault(code, {"group_code": code, "section_type": {}, "places": {}})
            g["section_type"][lang] = section
            poi = poi_theo_uuid.get(uid)
            p = g["places"].setdefault(uid, {"row_uuid": uid,
                                             "row_key": f"{pid}:SURROUNDING:{poi}" if poi else None})
            p.setdefault(lang, {})[ten] = gt
    out = []
    for h in ra.values():
        h["POLICY"] = list(h.pop("_policy").values())
        sur = h.pop("_sur")
        h["SURROUNDING"] = [{**g, "places": list(g["places"].values())}
                            for g in sorted(sur.values(), key=lambda x: x["group_code"])]
        out.append(h)
    return out


def ghi_json(ks: dict, ra: Path, *, tach_file: bool = False, pham_vi: str = "") -> tuple[int, int]:
    """Ghi JSON; trả về (số khách sạn, số bản ghi 7 cột)."""
    hotels = gom(ks)
    so_dong = sum(1 for d in sinh_dong(ks) if d[8] is not None and str(d[8]).strip() != "")
    if tach_file:
        ra.mkdir(parents=True, exist_ok=True)
        for h in hotels:
            slug = re.sub(r"[^a-z0-9]+", "_", (h["hotel_name"] or "").lower()).strip("_")[:60]
            (ra / f"{h['property_id']}_{slug}.json").write_text(
                json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        ra.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_table": BANG, "columns": CAC_COT,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scope": pham_vi or None, "hotel_count": len(hotels), "row_count": so_dong,
            "note": "Mỗi khách sạn gom theo type; row_uuid = md5(row_key)::uuid. "
                    "Field room_count / tripAdvisorId có thể vắng ở một số khách sạn.",
            "hotels": hotels,
        }
        ra.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(hotels), so_dong


def main(args) -> int:
    thu_muc = Path(args.thu_muc_raw)
    if not thu_muc.is_absolute():
        thu_muc = ROOT / thu_muc
    chi_ids = set(args.ids) if args.ids else None
    if args.ids_file:
        chi_ids = (chi_ids or set()) | {x.strip() for x in Path(args.ids_file).read_text(encoding="utf-8").split()
                                        if x.strip() and not x.startswith("#")}
    ks = doc_raw(thu_muc, chi_ids)
    if not ks:
        print("Không có khách sạn nào để xuất.", file=sys.stderr)
        return 1
    ra = Path(args.ra)
    if not ra.is_absolute():
        ra = ROOT / ra
    n_ks, n_dong = ghi_json(ks, ra, tach_file=args.tach_file)
    print(f"Đã xuất JSON {ra}: {n_ks} khách sạn, {n_dong} bản ghi")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--thu-muc-raw", default="output/details/raw")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--ids-file")
    ap.add_argument("--ra", required=True, help="file .json, hoặc thư mục khi --tach-file")
    ap.add_argument("--tach-file", action="store_true", help="mỗi khách sạn một file trong thư mục --ra")
    sys.exit(main(ap.parse_args()))
