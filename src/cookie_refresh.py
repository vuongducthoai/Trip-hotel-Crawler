"""Lấy cookie lần lượt cho các ngôn ngữ mà người dùng chọn."""
from __future__ import annotations

import argparse
import asyncio

from crawl_fast import export_cookies


async def main(languages: list[str]) -> None:
    for lang in languages:
        locale, currency = ("vi-VN", "VND") if lang == "vi" else ("en-US", "USD")
        print(f"Lấy cookie cho {locale}…")
        await export_cookies(locale, currency, 45)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--languages", nargs="+", choices=("vi", "en"), required=True)
    asyncio.run(main(parser.parse_args().languages))
