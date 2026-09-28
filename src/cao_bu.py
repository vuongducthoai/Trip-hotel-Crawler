"""Cào bù: cào lại đúng các khách sạn được chọn, ghi đè raw cũ.

    python src/cao_bu.py --ids-file output/ids/cao_bu.txt --languages vi en

Khác crawl_pipeline: không lấy danh sách, không cần cityId; luôn --force để
raw thiếu mô tả/chính sách/lân cận được thay bằng bản mới.
"""
from __future__ import annotations

import argparse
import re
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import crawl_fast  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARKETS = {"vi": ("vi-VN", "VND"), "en": ("en-US", "USD")}


def main(args) -> int:
    ids = [x for x in re.split(r"\s+", Path(args.ids_file).read_text(encoding="utf-8").strip()) if x]
    if not ids:
        print("Không có ID nào để cào bù.")
        return 2
    che_do = "bỏ qua khách sạn đã đủ" if getattr(args, "bo_qua_da_co", False) else "cào lại tất cả"
    print(f"{getattr(args, 'nhan', 'CÀO BÙ')} · {len(ids)} khách sạn · ngôn ngữ: {', '.join(args.languages)} · {che_do}")
    worst = 0
    for index, lang in enumerate(args.languages, 1):
        locale, currency = MARKETS[lang]
        print(f"NGÔN NGỮ {index}/{len(args.languages)} · {locale}")
        detail_args = Namespace(
            export_cookies=False, cookie_wait=45, chi_dump=True,
            force=not getattr(args, "bo_qua_da_co", False),
            hotel_id=None, ids=ids, ids_file=None, file=None,
            locale=locale, currency=currency, checkin=None, checkout=None,
            limit=len(ids), delay=2.0, jitter=1.5, concurrency=1, timeout=30.0,
            into_raw=True,
        )
        code = crawl_fast.main(detail_args) or 0
        worst = max(worst, code)
        if code and code != 3:
            return code
    print("CÀO BÙ XONG." if not worst else "CÀO BÙ HOÀN THÀNH MỘT PHẦN.")
    return worst


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids-file", required=True)
    parser.add_argument("--languages", nargs="+", choices=("vi", "en"), required=True)
    parser.add_argument("--bo-qua-da-co", action="store_true", help="không cào lại raw đã hoàn chỉnh")
    parser.add_argument("--nhan", default="CÀO BÙ", help="nhãn in ở dòng đầu log")
    raise SystemExit(main(parser.parse_args()))
