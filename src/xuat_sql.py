"""Xuất raw → file .sql (PostgreSQL) cho bảng trip_tmp_property_translation.

Dùng chung doc_raw()/sinh_dong() với xuat_csv.py nên SQL và CSV luôn khớp nhau
(cùng row_uuid, cùng HTML chính sách, cùng cách làm tròn). Chỉ khác định dạng.

    python src/xuat_sql.py --ra output/csv/dump.sql
    python src/xuat_sql.py --ids-file output/ids/x.txt --bang splatform_meta.trip_tmp_property_translation
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xuat_csv import CAC_COT, doc_raw, sinh_dong  # noqa: E402

BANG_MAC_DINH = "splatform_meta.trip_tmp_property_translation"
BANG_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
LO = 500   # số bản ghi mỗi câu INSERT


def kiem_tra_ten_bang(bang: str) -> str:
    bang = (bang or "").strip() or BANG_MAC_DINH
    if not BANG_RE.match(bang):
        raise ValueError("Tên bảng không hợp lệ (chỉ chữ, số, gạch dưới, tối đa một dấu chấm schema.bang).")
    return bang


def sql_str(value) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def create_table_sql(bang: str) -> str:
    parts = []
    if "." in bang:
        parts.append(f"CREATE SCHEMA IF NOT EXISTS {bang.split('.', 1)[0]};")
    parts.append(
        f"CREATE TABLE IF NOT EXISTS {bang} (\n"
        "  row_uuid uuid NOT NULL,\n"
        "  property_id bigint NOT NULL,\n"
        "  type text NOT NULL,\n"
        "  section_type text,\n"
        "  lang text NOT NULL,\n"
        "  field text NOT NULL,\n"
        "  value text,\n"
        "  UNIQUE (row_uuid, lang, field)\n"
        ");"
    )
    return "\n".join(parts)


def ghi_sql(ks: dict, ra: Path, *, bang: str = BANG_MAC_DINH, on_conflict: bool = True,
            tung_dong: bool = False, create_table: bool = False, pham_vi: str = "") -> tuple[int, int]:
    """Ghi file .sql; trả về (số khách sạn, số bản ghi)."""
    bang = kiem_tra_ten_bang(bang)
    dong = [d for d in sinh_dong(ks) if d[8] is not None and str(d[8]).strip() != ""]
    dong.sort(key=lambda d: (d[0], d[1], d[2], d[3]))
    cot = ", ".join(CAC_COT)
    conflict = (" ON CONFLICT (row_uuid, lang, field) DO UPDATE SET value = EXCLUDED.value, "
                "property_id = EXCLUDED.property_id, type = EXCLUDED.type, section_type = EXCLUDED.section_type"
                if on_conflict else "")

    def gia_tri(d) -> str:
        pid, lang, _, _, uid, loai, section, ten, gt = d
        return f"({sql_str(uid)}, {int(pid)}, {sql_str(loai)}, {sql_str(section)}, {sql_str(lang)}, {sql_str(ten)}, {sql_str(gt)})"

    ra.parent.mkdir(parents=True, exist_ok=True)
    with ra.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"-- Trip Hotel Data · dump PostgreSQL cho {bang}\n")
        f.write(f"-- Tạo lúc {datetime.now().isoformat(timespec='seconds')}"
                + (f" · phạm vi: {pham_vi}" if pham_vi else "") + "\n")
        f.write(f"-- {len(ks)} khách sạn · {len(dong)} bản ghi · cột: {cot}\n")
        f.write("-- Nạp: psql -h <host> -U <user> -d <db> -f <file này>\n")
        f.write("SET client_encoding = 'UTF8';\nBEGIN;\n")
        if create_table:
            f.write(create_table_sql(bang) + "\n")
        if tung_dong:
            for d in dong:
                f.write(f"INSERT INTO {bang} ({cot}) VALUES {gia_tri(d)}{conflict};\n")
        else:
            for i in range(0, len(dong), LO):
                chunk = dong[i:i + LO]
                f.write(f"INSERT INTO {bang} ({cot}) VALUES\n")
                f.write(",\n".join(gia_tri(d) for d in chunk))
                f.write(f"{conflict};\n")
        f.write("COMMIT;\n")
    return len(ks), len(dong)


def main(args) -> int:
    thu_muc = Path(args.thu_muc_raw)
    if not thu_muc.is_absolute():
        thu_muc = ROOT / thu_muc
    chi_ids = None
    if args.ids_file:
        chi_ids = {d.strip() for d in Path(args.ids_file).read_text(encoding="utf-8").splitlines() if d.strip()}
    if args.ids:
        chi_ids = (chi_ids or set()) | set(args.ids)
    ks = doc_raw(thu_muc, chi_ids)
    if not ks:
        print("Không có khách sạn nào để xuất.", file=sys.stderr)
        return 1
    ra = Path(args.ra)
    if not ra.is_absolute():
        ra = ROOT / ra
    n_ks, n_dong = ghi_sql(ks, ra, bang=args.bang, on_conflict=not args.khong_on_conflict,
                           tung_dong=args.tung_dong, create_table=args.create_table)
    print(f"Đã ghi {ra} · {n_ks} khách sạn · {n_dong} bản ghi")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--thu-muc-raw", default="output/details/raw")
    ap.add_argument("--ids-file")
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--ra", required=True)
    ap.add_argument("--bang", default=BANG_MAC_DINH)
    ap.add_argument("--khong-on-conflict", action="store_true")
    ap.add_argument("--tung-dong", action="store_true")
    ap.add_argument("--create-table", action="store_true")
    raise SystemExit(main(ap.parse_args()))
