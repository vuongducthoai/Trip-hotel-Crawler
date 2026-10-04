"""Chạy trọn một lượt: lấy danh sách rồi crawl chi tiết cho các ngôn ngữ đã chọn."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from argparse import Namespace

import config
import crawl_api
import crawl_fast


def newest_list(city_id: int, locale: str, currency: str):
    tag = f"{locale}_{currency}".replace("-", "")
    files = list(config.DATA_DIR.glob(f"api_hotels_{city_id}_{tag}_*.json"))
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def combined_ids(source, city_id: int, locale: str, currency: str, limit: int) -> list[str]:
    """Gộp ID của lượt mới với checkpoint cũ để tiếp tục thay vì quay lại từ đầu."""
    tag = f"{locale}_{currency}".replace("-", "")
    older = sorted(
        config.DATA_DIR.glob(f"api_hotels_{city_id}_{tag}_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    paths = [source, *(path for path in older if path != source)]
    ids: list[str] = []
    seen: set[str] = set()
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for hotel in payload.get("hotels") or []:
            hotel_id = str(hotel.get("trip_hotel_id") or "")
            if hotel_id and hotel_id not in seen:
                seen.add(hotel_id)
                ids.append(hotel_id)
                if len(ids) >= limit:
                    return ids
    return ids


def main(args) -> int:
    markets = [("vi-VN", "VND") if lang == "vi" else ("en-US", "USD")
               for lang in args.languages]
    list_locale, list_currency = markets[0]
    continue_mode = bool(getattr(args, "continue_mode", False))
    complete_by_market = {
        (locale, currency): crawl_fast.complete_city_ids(args.city_id, locale, currency)
        for locale, currency in markets
    }
    known_ids = set().union(*complete_by_market.values()) if complete_by_market else set()
    target_total = len(known_ids) + args.limit if continue_mode else args.limit
    if continue_mode:
        print(f"CHẾ ĐỘ ĐỒNG BỘ THÊM · Đã có {len(known_ids)} khách sạn, "
              f"cần tìm thêm {args.limit} → mục tiêu {target_total}.")
    print(f"BƯỚC 1/2 · Lấy tối đa {target_total} khách sạn tại {args.city_name}…")
    list_args = Namespace(
        locale=list_locale,
        currency=list_currency,
        city=None,
        city_id=args.city_id,
        city_name=args.city_name,
        province_id=args.province_id,
        country_id=args.country_id,
        country_name=args.country_name,
        max_pages=None,
        limit=target_total,
        target_count=target_total,
        profile_dir=None,
        allow_recommend=False,
    )
    try:
        asyncio.run(crawl_api.main(list_args))
    except SystemExit as exc:
        print(f"Không lấy được danh sách: {exc}")
        return int(exc.code) if isinstance(exc.code, int) else 1
    except Exception as exc:
        message = str(exc)
        if "ERR_NETWORK_ACCESS_DENIED" in message:
            print("Chrome bị Windows hoặc phần mềm bảo mật từ chối truy cập mạng.")
            print("Hãy đóng app, mở Chrome bình thường để kiểm tra Trip.com, rồi mở lại app.")
            print("Nếu vẫn lỗi, cho phép Google Chrome qua Firewall/antivirus và thử lại.")
        elif "ERR_" in message:
            print(f"Chrome không mở được trang Trip.com: {message.splitlines()[0]}")
            print("Hãy kiểm tra mạng, VPN/proxy và bấm Làm mới phiên Trip.com trước khi thử lại.")
        else:
            print(f"Không lấy được danh sách: {type(exc).__name__}: {message}")
        return 1

    source = newest_list(args.city_id, list_locale, list_currency)
    if source is None:
        print("Không tìm thấy file danh sách vừa tạo.")
        return 1
    ids = combined_ids(source, args.city_id, list_locale, list_currency, target_total)
    print(f"BƯỚC 2/2 · Có {len(ids)}/{target_total} khách sạn duy nhất từ danh sách mới + checkpoint cũ")
    partial = len(ids) < target_total
    had_work = False
    for index, (locale, currency) in enumerate(markets, 1):
        print(f"NGÔN NGỮ {index}/{len(markets)} · {locale}")
        detail_ids = ids
        if continue_mode:
            complete_ids = complete_by_market[(locale, currency)]
            detail_ids = [hotel_id for hotel_id in ids if hotel_id not in complete_ids][:args.limit]
            print(f"  • Đã hoàn chỉnh: {len(complete_ids)} · ID mới/thiếu sẽ đồng bộ: "
                  f"{len(detail_ids)}/{args.limit}")
            if len(detail_ids) < args.limit:
                partial = True
            if not detail_ids:
                print("  ⚠ Chưa tìm thấy ID mới trong danh sách Trip.com và các checkpoint hiện có.")
                continue
        had_work = True
        detail_args = Namespace(
            export_cookies=False,
            cookie_wait=45,
            chi_dump=True,
            force=False,
            hotel_id=None,
            ids=detail_ids,
            ids_file=None,
            file=None,
            locale=locale,
            currency=currency,
            checkin=None,
            checkout=None,
            limit=len(detail_ids),
            delay=2.0,
            jitter=1.5,
            concurrency=1,
            timeout=30.0,
            into_raw=True,
        )
        result = crawl_fast.main(detail_args)
        if result:
            return result
    if had_work:
        import tripadvisor
        tripadvisor.ghep_sau_crawl(ids)
    if continue_mode and not had_work:
        print("CHƯA ĐỒNG BỘ THÊM ĐƯỢC: Trip.com chưa cung cấp ID khách sạn mới. "
              "Dữ liệu cũ được giữ nguyên; hãy thử lại sau.")
        return 3
    if partial:
        print("HOÀN THÀNH MỘT PHẦN: đã đồng bộ mọi ID mới tìm được nhưng chưa đạt số lượng yêu cầu.")
        return 3
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city-id", type=int, required=True)
    parser.add_argument("--province-id", type=int, default=0)
    parser.add_argument("--country-id", type=int, required=True)
    parser.add_argument("--city-name", required=True)
    parser.add_argument("--country-name", default="Việt Nam")
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--continue-mode", action="store_true")
    parser.add_argument("--languages", nargs="+", choices=("vi", "en"), required=True)
    raise SystemExit(main(parser.parse_args()))
