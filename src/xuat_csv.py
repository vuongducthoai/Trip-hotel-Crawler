"""Xuất thẳng raw JSON → CSV cho anh mentor, KHÔNG cần PostgreSQL.

Bản CSV này phải ra ĐÚNG những dòng mà scripts/export_trip_property_translation.sql
sinh ra từ DB — chỉ khác định dạng (CSV thay vì câu INSERT). Mọi thay đổi ở một
bên phải chép sang bên kia, nếu không dữ liệu anh mentor nhận sẽ lệch.

    python src/xuat_csv.py                                  # tất cả raw đã crawl
    python src/xuat_csv.py --ids-file output/ids/thu_hk.txt # chỉ vài khách sạn
    python src/xuat_csv.py --ra output/csv/hongkong.csv
    python src/xuat_csv.py --thu-muc-raw output/details/raw

Ra một file CSV 7 cột, khớp thẳng bảng trip_tmp_property_translation:
    property_id, row_uuid, type, section_type, lang, field, value

Field tripAdvisorId (type DESCRIPTION) lấy từ kết quả ghép của src/tripadvisor.py;
khách sạn chưa ghép hoặc ghép chưa chắc (review) thì không có dòng này.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import raw_store                      # noqa: E402
import tripadvisor                    # noqa: E402
from v2.extract import build_bundle   # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------
# Các hằng số phải khớp export_trip_property_translation.sql
# --------------------------------------------------------------------------

# Mục chính sách KHÔNG xuất. 'credit' = phương thức thanh toán, anh Thoại yêu
# cầu bỏ (2026-09-24) vì Trip.com trả phần này chủ yếu bằng ảnh logo thẻ.
MUC_BO_QUA = {"credit"}

# Mã quốc gia ISO 3166-1 alpha-2 theo countryId của Trip.com.
# CẢNH BÁO: Trip.com xếp Hồng Kông vào countryId = 1 (Trung Quốc), nên khách
# sạn Hồng Kông sẽ ra 'CN' chứ không phải 'HK'. Nếu anh mentor cần đúng ISO thì
# phải tách theo provinceName, không dựa được vào countryId.
MA_QUOC_GIA = {
    111: "VN",
    27: "DK",
    107: "IN",
    1: "CN",
}

# Trip.com thỉnh thoảng trả tên POI placeholder kiểu "size?" — bỏ cả địa điểm.
TEN_POI_RAC = re.compile(r"^(size\?|n/?a|null|-+|\?+)$", re.IGNORECASE)

# Thứ tự cột theo yêu cầu 2026-09-29: property_id đứng đầu, row_uuid thứ hai.
CAC_COT = ["property_id", "row_uuid", "type", "section_type", "lang", "field", "value"]


def ma_uuid(khoa: str) -> str:
    """md5(khoa)::uuid của Postgres — hex 32 ký tự thành dạng 8-4-4-4-12."""
    return str(uuid.UUID(hashlib.md5(khoa.encode("utf-8")).hexdigest()))


def thoat_html(s: str) -> str:
    """Giống replace() lồng nhau trong SQL: chỉ & < > , không đụng dấu nháy."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lam_tron(so: Decimal, le: int) -> Decimal:
    """round() của numeric Postgres: làm tròn nửa lên, không phải nửa về chẵn."""
    return so.quantize(Decimal(1).scaleb(-le), rounding=ROUND_HALF_UP)


def chu_khoang_cach(km: Decimal | None) -> str | None:
    """< 1 km → '450m' · >= 1 km → '8,6km' (dấu phẩy, đúng như SQL)."""
    if km is None:
        return None
    if km < 1:
        return f"{int(lam_tron(km * 1000, 0))}m"
    return f"{lam_tron(km, 1)}".replace(".", ",") + "km"


def so_met(km: Decimal | None) -> str | None:
    return None if km is None else str(int(lam_tron(km * 1000, 0)))


def so_ra_chu(x: Any) -> str | None:
    """float8::text của Postgres dùng biểu diễn ngắn nhất — repr của Python cũng vậy."""
    if x is None:
        return None
    if isinstance(x, float):
        return repr(x)
    return str(x)


# --------------------------------------------------------------------------
# Gom dữ liệu từ raw
# --------------------------------------------------------------------------
@dataclass
class BanNgonNgu:
    """Một khách sạn ở MỘT thứ tiếng."""
    lang: str
    name: str | None = None
    local_name: str | None = None
    address: str | None = None
    description: str | None = None
    policy: list = dc_field(default_factory=list)    # (section_code, sort_order, title, lines)
    nearby: list = dc_field(default_factory=list)    # các M.NearbyPlace


@dataclass
class KhachSan:
    trip_hotel_id: str
    room_count: int | None = None
    trip_country_id: int | None = None
    ban: dict = dc_field(default_factory=dict)       # lang -> BanNgonNgu


def doc_raw(thu_muc_raw: Path, chi_ids: set[str] | None) -> dict[str, KhachSan]:
    """Đọc mọi raw, mỗi khách sạn lấy file MỚI NHẤT của từng thị trường.

    Giống newest_raw() của v2_loader: một khách sạn có thể có nhiều lần crawl,
    chỉ file mới nhất mới được tính.
    """
    moi_nhat: dict[tuple[str, str], tuple[float, Path]] = {}
    for duong in thu_muc_raw.rglob("*"):
        if not duong.is_file() or ".failed." in duong.name:
            continue
        if duong.suffix not in (".json", ".gz"):
            continue
        hid = raw_store.hotel_id(duong)
        if not hid.isdigit() or (chi_ids and hid not in chi_ids):
            continue
        # .../raw/<locale>/<currency>/<id>.json.gz
        try:
            locale, currency = duong.parent.parent.name, duong.parent.name
        except Exception:
            continue
        if "-" not in locale:
            continue
        khoa = (hid, f"{locale}/{currency}")
        mtime = duong.stat().st_mtime
        if khoa not in moi_nhat or mtime > moi_nhat[khoa][0]:
            moi_nhat[khoa] = (mtime, duong)

    ks: dict[str, KhachSan] = {}
    loi = 0
    for (hid, thi_truong), (_, duong) in sorted(moi_nhat.items()):
        locale, currency = thi_truong.split("/")
        try:
            dump = raw_store.read(duong)
            b, _ = build_bundle(dump, raw_locale=locale, currency=currency,
                                raw_path=str(duong), file_hotel_id=hid)
        except Exception:
            loi += 1
            continue
        if b is None or b.hotel_i18n is None:
            loi += 1
            continue
        muc = ks.setdefault(hid, KhachSan(trip_hotel_id=hid))
        # room_count / quốc gia không phụ thuộc ngôn ngữ — giữ giá trị đầu tiên có
        if muc.room_count is None and b.hotel is not None:
            muc.room_count = b.hotel.room_count
        if muc.trip_country_id is None and b.country is not None:
            muc.trip_country_id = b.country.trip_country_id
        i18n = b.hotel_i18n
        muc.ban[b.locale] = BanNgonNgu(
            lang=b.locale, name=i18n.name, local_name=i18n.local_name,
            address=i18n.address, description=i18n.description,
            policy=[(s.section_code, s.sort_order, s.title, list(s.lines))
                    for s in b.policy_sections],
            nearby=list(b.nearby),
        )
    if loi:
        print(f"  (bỏ qua {loi} raw không đọc được)", file=sys.stderr)
    return ks


def toa_do_poi(ks: dict[str, KhachSan]) -> dict[int, tuple]:
    """Một toạ độ duy nhất cho mỗi trip_poi_id, lấy theo thứ tự vi → en.

    Trip.com đôi khi trả toạ độ hơi khác nhau cho CÙNG một POI ở hai thứ tiếng
    (gặp 3 POI trong 20 khách sạn Hồng Kông). Bảng v2.places chỉ giữ một dòng
    mỗi POI nên bản nào nạp trước thì thắng — nghĩa là file dump từ DB phụ
    thuộc thứ tự nạp. Ở đây chốt cứng thứ tự để chạy lại bao nhiêu lần cũng ra
    một kết quả.
    """
    ra: dict[int, tuple] = {}
    for lang_uu_tien in ("vi", "en"):
        for muc in ks.values():
            ban = muc.ban.get(lang_uu_tien)
            if not ban:
                continue
            for p in ban.nearby:
                if p.trip_poi_id not in ra and p.latitude is not None:
                    ra[p.trip_poi_id] = (p.latitude, p.longitude)
    return ra


def ten_nhom_du_phong(ks: dict[str, KhachSan]) -> dict[tuple[str, int], str]:
    """Tên phổ biến nhất của mỗi (ngôn ngữ, mã nhóm) — dùng khi Trip.com bỏ trống.

    SQL tính trên TOÀN BỘ DB; ở đây chỉ tính trên các khách sạn đang xuất. Crawl
    một thành phố ít khách sạn thì phần dự phòng này mỏng hơn, section_type có
    thể rơi thành số trần ('03' thay vì '03_Điểm nổi bật').
    """
    dem: dict[tuple[str, int], Counter] = defaultdict(Counter)
    for muc in ks.values():
        for ban in muc.ban.values():
            for p in ban.nearby:
                ten = (p.group_name or "").strip()
                if ten:
                    dem[(ban.lang, p.group_code)][ten] += 1
    ra: dict[tuple[str, int], str] = {}
    for khoa, c in dem.items():
        # nhiều nhất trước, hoà thì lấy theo thứ tự chữ cái — giống ORDER BY của SQL
        ra[khoa] = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return ra


# --------------------------------------------------------------------------
# Dựng HTML chính sách — phải khớp CTE mau_html trong SQL
# --------------------------------------------------------------------------
def html_mo_ta(mo_ta: str | None) -> str | None:
    """Mô tả: mỗi đoạn (cách nhau bằng xuống dòng) bọc một <p>, giống policy_content.

    Đổi 2026-09-28 theo yêu cầu anh Bo: để text thuần xuống dòng thì lúc đưa lên
    web dễ bị dính thành một khối; HTML <p> hiển thị thẳng được.
    """
    if not mo_ta:
        return None
    doan = [" ".join(d.split()) for d in mo_ta.replace("\r", "\n").split("\n")]
    doan = [d for d in doan if d]
    return "".join(f"<p>{thoat_html(d)}</p>" for d in doan) or None


def html_chinh_sach(lines: list) -> str:
    """Mỗi dòng một <p>, giữ thứ tự. Dòng in_table liền nhau bọc <table>.

    Dòng có nhãn  → <p>Nhận phòng: <strong>Sau 14:00</strong></p>
    Hàng của bảng → <tr><td>Người lớn</td><td>229,00 HK$</td></tr>
    """
    manh: list[str] = []
    n = len(lines)
    for i, dong in enumerate(lines):
        nhan, chu, trong_bang = (list(dong) + [False])[:3]
        nhan = (nhan or "").strip()
        chu = thoat_html(chu or "")
        if not trong_bang:
            manh.append(f"<p>{thoat_html(nhan)}: <strong>{chu}</strong></p>" if nhan
                        else f"<p>{chu}</p>")
            continue
        truoc = (list(lines[i - 1]) + [False])[2] if i > 0 else False
        sau = (list(lines[i + 1]) + [False])[2] if i + 1 < n else False
        o = (f"<td>{thoat_html(nhan)}</td><td>{chu}</td>" if nhan
             else f'<td colspan="2">{chu}</td>')
        manh.append(("<table>" if truoc is not True else "")
                    + f"<tr>{o}</tr>"
                    + ("</table>" if sau is not True else ""))
    return "".join(manh)


# --------------------------------------------------------------------------
# Sinh dòng
# --------------------------------------------------------------------------
def sinh_dong(ks: dict[str, KhachSan]) -> Iterable[tuple]:
    """Trả (property_id, lang, ord, sub, row_uuid, type, section_type, field, value)."""
    nhom_dp = ten_nhom_du_phong(ks)
    toa_do = toa_do_poi(ks)
    # Kết quả ghép Tripadvisor (output/tripadvisor/<id>.json) — chỉ 'matched' mới có ID.
    ta = tripadvisor.doc_tat_ca()

    for hid, muc in ks.items():
        pid = int(hid)
        iso2 = MA_QUOC_GIA.get(muc.trip_country_id)
        ta_id = tripadvisor.tripadvisor_id(ta.get(hid))

        for lang, ban in muc.ban.items():
            # ------------------------------------------------ DESCRIPTION
            uid = ma_uuid(f"{hid}:DESCRIPTION")
            truong = [
                ("hotel_name", ban.name, 1),
                ("local_name", ban.local_name, 2),
                ("hotel_address", ban.address, 3),
                ("countryCode", iso2, 4),
                ("room_count", None if muc.room_count is None else str(muc.room_count), 5),
                ("description", html_mo_ta(ban.description), 6),
                ("tripAdvisorId", ta_id, 7),
            ]
            for ten, gt, sub in truong:
                yield (pid, lang, 1, sub, uid, "DESCRIPTION", "hotelInfo", ten, gt)

            # ------------------------------------------------ POLICY
            for ma, thu_tu, tieu_de, lines in ban.policy:
                if ma in MUC_BO_QUA:
                    continue
                uid = ma_uuid(f"{hid}:POLICY:{ma}")
                thu_tu = thu_tu or 0
                yield (pid, lang, 2, thu_tu * 10, uid, "POLICY", ma,
                       "policy_title", tieu_de)
                if lines:
                    yield (pid, lang, 2, thu_tu * 10 + 1, uid, "POLICY", ma,
                           "policy_content", html_chinh_sach(lines))

            # ------------------------------------------------ SURROUNDING
            for p in ban.nearby:
                ten_poi = (p.name or "").strip()
                if not ten_poi or TEN_POI_RAC.match(ten_poi):
                    continue
                ten_nhom = (p.group_name or "").strip() or nhom_dp.get((lang, p.group_code), "")
                section = f"{p.group_code:02d}" + (f"_{ten_nhom}" if ten_nhom else "")
                uid = ma_uuid(f"{hid}:SURROUNDING:{p.trip_poi_id}")
                goc = (p.sort_order or 0) * 10
                km = p.distance_km
                lat, lng = toa_do.get(p.trip_poi_id, (p.latitude, p.longitude))
                for ten, gt, sub in [
                    ("surrounding_name", p.name, 1),
                    ("surrounding_kind", (p.kind or "").strip() or None, 2),
                    ("surrounding_label", (p.type_label or "").strip() or None, 3),
                    ("surrounding_distance", chu_khoang_cach(km), 4),
                    ("surrounding_distance_m", so_met(km), 5),
                    ("surrounding_lat", so_ra_chu(lat), 6),
                    ("surrounding_lng", so_ra_chu(lng), 7),
                ]:
                    yield (pid, lang, 3, goc + sub, uid, "SURROUNDING", section, ten, gt)


def main(args) -> int:
    thu_muc = Path(args.thu_muc_raw)
    if not thu_muc.is_absolute():
        thu_muc = ROOT / thu_muc
    if not thu_muc.exists():
        print(f"Không thấy thư mục raw: {thu_muc}", file=sys.stderr)
        return 1

    chi_ids = None
    if args.ids_file:
        duong = Path(args.ids_file)
        if not duong.is_absolute():
            duong = ROOT / duong
        chi_ids = {d.strip() for d in duong.read_text(encoding="utf-8").splitlines()
                   if d.strip() and not d.startswith("#")}
    if args.ids:
        chi_ids = (chi_ids or set()) | set(args.ids)

    print(f"Đọc raw từ {thu_muc}" + (f" (lọc {len(chi_ids)} id)" if chi_ids else ""))
    ks = doc_raw(thu_muc, chi_ids)
    if not ks:
        print("Không có khách sạn nào để xuất.", file=sys.stderr)
        return 1

    dong = [d for d in sinh_dong(ks)
            if d[8] is not None and str(d[8]).strip() != ""]
    dong.sort(key=lambda d: (d[0], d[1], d[2], d[3]))

    ra = Path(args.ra)
    if not ra.is_absolute():
        ra = ROOT / ra
    ra.parent.mkdir(parents=True, exist_ok=True)
    # newline="" để module csv tự xử lý xuống dòng trong ô (mô tả nhiều đoạn)
    with ra.open("w", encoding="utf-8-sig" if args.bom else "utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        w.writerow(CAC_COT)
        for pid, lang, _, _, uid, loai, section, ten, gt in dong:
            w.writerow([pid, uid, loai, section, lang, ten, gt])
    return _tom_tat(ks, dong, ra)


def _tom_tat(ks, dong, ra) -> int:
    theo_loai = Counter(d[5] for d in dong)
    theo_lang = Counter(d[1] for d in dong)
    print(f"\nĐã ghi {ra}")
    print(f"  {len(ks)} khách sạn · {len(dong):,} dòng")
    print("  theo type :", dict(theo_loai))
    print("  theo lang :", dict(theo_lang))
    thieu = [h for h, m in ks.items()
             if not any(b.description for b in m.ban.values())]
    if thieu:
        print(f"  ⚠ {len(thieu)} khách sạn không có mô tả ở bất kỳ ngôn ngữ nào")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Raw JSON → CSV cho anh mentor (không cần PostgreSQL)")
    ap.add_argument("--thu-muc-raw", default="output/details/raw")
    ap.add_argument("--ids", nargs="+", help="chỉ các trip_hotel_id này")
    ap.add_argument("--ids-file", help="file id, mỗi dòng một id")
    ap.add_argument("--ra", default="output/csv/trip_property_translation.csv")
    ap.add_argument("--bom", action="store_true",
                    help="thêm BOM để Excel mở tiếng Việt không lỗi font")
    sys.exit(main(ap.parse_args()))
