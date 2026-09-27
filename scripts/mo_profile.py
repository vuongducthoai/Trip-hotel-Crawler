"""Mở Chrome profile của tool đủ lâu để đăng nhập Trip.com, tìm thử thành phố,
giải captcha nếu có — rồi tự lưu cookie cho thị trường đó.

    python scripts/mo_profile.py --lang en            # en-US/USD, mở 5 phút
    python scripts/mo_profile.py --lang vi --phut 10  # vi-VN/VND, mở 10 phút

Trong cửa sổ Chrome: đăng nhập → chọn đúng ngôn ngữ/tiền tệ → tìm thử
"Hong Kong" và cuộn vài lần cho danh sách tải thêm → giữ cửa sổ mở tới khi
script tự đóng. Phải tắt server/tác vụ đang dùng cùng profile trước khi chạy.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from crawl_fast import export_cookies  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", choices=("vi", "en"), required=True)
    ap.add_argument("--phut", type=float, default=5, help="số phút giữ cửa sổ mở (mặc định 5)")
    args = ap.parse_args()
    locale, currency = ("vi-VN", "VND") if args.lang == "vi" else ("en-US", "USD")
    asyncio.run(export_cookies(locale, currency, int(args.phut * 60)))
