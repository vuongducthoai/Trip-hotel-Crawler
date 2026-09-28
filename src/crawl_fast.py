"""Crawl mô tả, chính sách và địa điểm lân cận bằng HTTP thuần.

Giữ nhịp nghỉ của repo gốc. Không crawl phòng, giá, ảnh, tiện nghi hoặc đánh giá;
không xoay IP và dừng ngay khi Trip.com trả dấu hiệu chặn.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import config
import raw_store
from api_extract import _next_f_text
from block_detect import blocked_reason as api_blocked
from detail_extract import extract_detail
from hotel_description import description_from_scripts, description_text

JSON_DECODER = json.JSONDecoder()
DETAIL_BLOCK_URL = "embedded:hotel-detail-response"
NEARBY_URL = "/restapi/soa2/28820/ctGetNearbyPlaceInfo"
MARKET_HOST = {"vi-VN": "vn.trip.com", "en-US": "www.trip.com"}
BLOCK_MARKERS = ("htlSpiderActionErrorCode", "Antibot", "/account/signin",
                 "c-slide-captcha", "challenge_page", "Antibot-Gray-ip")
SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)


def detail_block(html_source: str) -> dict | None:
    try:
        content = _next_f_text(html_source)
    except Exception:
        return None
    anchor = '"hotelDetailResponse":'
    index = content.find(anchor)
    if index < 0:
        return None
    start = index + len(anchor)
    while start < len(content) and content[start].isspace():
        start += 1
    try:
        value, _ = JSON_DECODER.raw_decode(content, start)
    except ValueError:
        return None
    return value if isinstance(value, dict) and value.get("hotelBaseInfo") else None


def description_packet(html_source: str, hotel_id: str) -> dict | None:
    info = description_from_scripts(SCRIPT.findall(html_source), hotel_id)
    if not description_text(info):
        return None
    return {"hotel_id": str(hotel_id), "hotelDescriptionInfo": info}


def blocked_html(html_source: str, final_url: str) -> str | None:
    if "/account/signin" in final_url.lower():
        return "bị chuyển sang trang đăng nhập"
    for marker in BLOCK_MARKERS:
        if marker in html_source:
            return f"HTML chứa dấu hiệu chặn: {marker}"
    return None


def cookie_file(locale: str, currency: str) -> Path:
    return config.OUTPUT_DIR / f"cookies_{locale}_{currency.upper()}.json"


async def export_cookies(locale: str, currency: str, wait_seconds: int = 45) -> Path:
    """Mở Chrome thật để người dùng đăng nhập, rồi lưu cookie của profile."""
    from playwright.async_api import async_playwright

    target = cookie_file(locale, currency)
    print(f"Chrome sẽ mở trong {wait_seconds} giây. Hãy đăng nhập Trip.com nếu cần và giữ cửa sổ mở.")
    async with async_playwright() as playwright:
        options = {
            "user_data_dir": str(config.profile_dir(locale, currency)),
            "channel": "msedge",
            "headless": False,
            "locale": locale,
            "timezone_id": config.TIMEZONE,
            "viewport": config.VIEWPORT,
            "args": ["--disable-quic"],
        }
        proxy = config.browser_proxy()
        if proxy:
            options["proxy"] = proxy
        context = await playwright.chromium.launch_persistent_context(**options)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(f"https://{MARKET_HOST.get(locale, 'www.trip.com')}/hotels/",
                            wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(wait_seconds * 1000)
            cookies = await context.cookies()
        finally:
            await context.close()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    print(f"Đã lưu {len(cookies)} cookie → {target}")
    return target


def load_cookies(locale: str, currency: str) -> tuple[dict, str | None]:
    path = cookie_file(locale, currency)
    if not path.exists():
        # Thiếu cookie cho thị trường này (vd. chỉ bấm 'Lấy lại cookie' cho vi
        # rồi crawl en) → tự lấy một lần thay vì dừng cả tác vụ.
        print(f"Chưa có cookie cho {locale}/{currency.upper()} → tự lấy cookie…")
        try:
            asyncio.run(export_cookies(locale, currency, 45))
        except Exception as exc:
            raise SystemExit(f"Không lấy được cookie cho {locale}/{currency.upper()} ({exc}). "
                             "Hãy bấm ‘Lấy lại cookie’ và chọn đủ ngôn ngữ trước khi crawl.")
    if not path.exists():
        raise SystemExit("Chưa có cookie. Hãy bấm ‘Lấy lại cookie’ trước khi crawl.")
    values = json.loads(path.read_text(encoding="utf-8"))
    cookies = {item["name"]: item["value"] for item in values if item.get("name")}
    return cookies, cookies.get("UBT_VID")


def headers_for(locale: str, currency: str, referer: str | None = None,
                json_api: bool = False) -> dict:
    host = MARKET_HOST.get(locale, "www.trip.com")
    origin = f"https://{host}"
    return {
        "User-Agent": config.USER_AGENT,
        "Accept": "application/json" if json_api else "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8" if locale.startswith("vi") else "en-US,en;q=0.9",
        "Origin": origin,
        "Referer": referer or f"{origin}/hotels/",
        "Content-Type": "application/json",
        # Trip.com kiểm tra cookieorigin theo đúng market host. Dùng www.trip.com
        # cho request của vn.trip.com khiến API trả thân rỗng dù HTTP vẫn là 200.
        "cookieorigin": origin,
        "currency": currency.upper(),
        "locale": locale,
        "Cache-Control": "no-cache",
    }


def detail_url(hotel_id: str, locale: str, currency: str, checkin: str, checkout: str) -> str:
    host = MARKET_HOST.get(locale, "www.trip.com")
    return (f"https://{host}/hotels/detail/?hotelId={hotel_id}&checkIn={checkin}"
            f"&checkOut={checkout}&adult=2&children=0&crn=1&curr={currency.upper()}&locale={locale}")


def nearby_body(detail: dict, hotel_id: str, locale: str, currency: str,
                checkin: str, checkout: str, visitor_id: str | None) -> dict:
    base = detail.get("hotelBaseInfo") or {}
    region = "VN" if locale == "vi-VN" else "US"
    visitor = visitor_id or ""
    return {
        "cityId": 0,
        "mapType": "gg",
        "masterHotelId": int(hotel_id),
        "oversea": True,
        "provinceId": base.get("provinceId") or 0,
        "head": {
            "platform": "PC", "cver": "0", "cid": visitor, "bu": "IBU",
            "group": "trip", "aid": "", "sid": "", "ouid": "",
            "locale": locale, "region": region, "timezone": "7",
            "currency": currency.upper(), "pageId": "10320668147", "vid": visitor,
            "guid": "", "isSSR": False,
            "extension": [
                {"name": "cityId", "value": ""},
                {"name": "checkIn", "value": checkin},
                {"name": "checkOut", "value": checkout},
            ],
        },
    }


def fetch_one(client, hotel_id: str, locale: str, currency: str,
              checkin: str, checkout: str, visitor_id: str | None) -> tuple[dict, str | None]:
    url = detail_url(hotel_id, locale, currency, checkin, checkout)
    response = client.get(url, headers=headers_for(locale, currency), follow_redirects=True)
    source = response.text
    reason = blocked_html(source, str(response.url))
    packets: list[dict] = []
    detail = None if reason else detail_block(source)
    if detail:
        packets.append({"url": DETAIL_BLOCK_URL, "method": "EMBEDDED", "status": 200,
                        "response": detail})
        described = description_packet(source, hotel_id)
        if described:
            packets.append({"url": "embedded:hotel-description", "method": "EMBEDDED",
                            "status": 200, "response": described})

        api_url = f"https://{MARKET_HOST.get(locale, 'www.trip.com')}{NEARBY_URL}"
        nearby_response = None
        try:
            nearby_response = client.post(
                api_url,
                headers=headers_for(locale, currency, referer=url, json_api=True),
                json=nearby_body(detail, hotel_id, locale, currency, checkin, checkout, visitor_id),
            )
            nearby_response.raise_for_status()
            nearby = nearby_response.json()
            api_reason = api_blocked(nearby)
            if api_reason:
                reason = f"API địa điểm lân cận bị chặn: {api_reason}"
                packets = []
            else:
                packets.append({"url": api_url, "method": "POST",
                                "status": nearby_response.status_code, "response": nearby})
        except Exception as exc:
            status = getattr(nearby_response, "status_code", "không có")
            reason = (f"API địa điểm lân cận không trả dữ liệu hợp lệ "
                      f"(HTTP {status}): {type(exc).__name__}: {exc}")
            packets = []

    normalized = extract_detail(packets, hotel_id, url, currency, locale)
    normalized.update(
        success=bool(detail) and reason is None,
        check_in=checkin,
        check_out=checkout,
        crawled_at=datetime.now().isoformat(timespec="seconds"),
        data_mode="chi-dump",
    )
    if reason:
        normalized["error"] = f"Trip.com chặn: {reason}"
    elif not detail:
        normalized["error"] = "HTML không có hotelDetailResponse; cookie có thể đã hết hạn."
    return {"target": {"hotel_id": hotel_id, "url": url}, "url": url,
            "normalized": normalized, "responses": packets}, reason


def save(dump: dict, hotel_id: str, locale: str, currency: str) -> Path:
    folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency.upper()
    folder.mkdir(parents=True, exist_ok=True)
    ok = (dump.get("normalized") or {}).get("success")
    name = f"{hotel_id}.json" if ok else f"{hotel_id}.failed.{datetime.now():%Y%m%d_%H%M%S}.json"
    if ok:
        # So với raw cũ (nếu có) để đánh dấu khách sạn có nội dung thay đổi.
        try:
            import thay_doi
            old_dump = saved_raw(hotel_id, locale, currency)
            thay_doi.ghi(thay_doi.so_sanh(old_dump, dump, hotel_id, locale, currency),
                         hotel_id, locale, currency)
        except Exception as exc:  # không để việc so sánh làm hỏng lượt crawl
            print(f"    (không so sánh được với raw cũ: {type(exc).__name__}: {exc})")
    return raw_store.write(folder / name, dump)


def raw_complete(dump: dict) -> bool:
    """Raw chỉ hoàn chỉnh khi đã lấy cả trang chi tiết và API surrounding.

    Không dựa vào số địa điểm vì một khách sạn có thể hợp lệ nhưng không có POI.
    Các raw cũ từng báo thành công nhưng thiếu packet surrounding sẽ được crawl lại.
    """
    if not (dump.get("normalized") or {}).get("success"):
        return False
    responses = dump.get("responses") or []
    has_detail = any(packet.get("url") == DETAIL_BLOCK_URL for packet in responses)
    has_nearby = any(NEARBY_URL in str(packet.get("url") or "") for packet in responses)
    return has_detail and has_nearby


def raw_city_info(dump: dict) -> dict | None:
    """Đọc thông tin thành phố từ packet chi tiết để lập dashboard."""
    for packet in dump.get("responses") or []:
        if packet.get("url") != DETAIL_BLOCK_URL:
            continue
        base = (packet.get("response") or {}).get("hotelBaseInfo") or {}
        try:
            city_id = int(base.get("cityId"))
        except (TypeError, ValueError):
            return None
        return {
            "city_id": city_id,
            "city_name": base.get("cityName") or base.get("provinceName") or f"Thành phố {city_id}",
            "province_id": base.get("provinceId") or 0,
            "country_id": base.get("countryId") or 0,
            "country_name": base.get("countryName") or "",
        }
    return None


def raw_city_id(dump: dict) -> int | None:
    info = raw_city_info(dump)
    return info["city_id"] if info else None


def saved_raw(hotel_id: str, locale: str, currency: str) -> dict | None:
    path = config.OUTPUT_DIR / "details" / "raw" / locale / currency.upper() / f"{hotel_id}.json"
    try:
        return raw_store.read(path)
    except (OSError, ValueError):
        return None


def complete_city_ids(city_id: int, locale: str, currency: str) -> set[str]:
    """Các khách sạn của thành phố đã đủ dữ liệu ở đúng thị trường/ngôn ngữ."""
    folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency.upper()
    result: set[str] = set()
    for path in raw_store.iter_raw_files(folder):
        hotel_id = raw_store.hotel_id(path)
        if not hotel_id.isdigit():
            continue
        try:
            dump = raw_store.read(path)
        except (OSError, ValueError):
            continue
        if raw_city_id(dump) == city_id and raw_complete(dump):
            result.add(hotel_id)
    return result


def read_ids(args) -> list[str]:
    if getattr(args, "ids", None):
        return [str(item) for item in args.ids]
    if args.hotel_id:
        return [str(args.hotel_id)]
    if args.ids_file:
        return [item for item in re.split(r"\s+", Path(args.ids_file).read_text(encoding="utf-8").strip()) if item]
    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        return [str(item["trip_hotel_id"]) for item in payload.get("hotels") or []]
    raise SystemExit("Cần --hotel-id, --ids-file hoặc --file.")


def default_stay() -> tuple[str, str]:
    from datetime import date, timedelta
    today = date.today()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7) + timedelta(days=7)
    return monday.isoformat(), (monday + timedelta(days=1)).isoformat()


def main(args) -> int:
    import httpx

    if args.export_cookies:
        asyncio.run(export_cookies(args.locale, args.currency, args.cookie_wait))
        return 0
    if not args.chi_dump:
        raise SystemExit("Ứng dụng này chỉ hỗ trợ chế độ --chi-dump.")

    ids = read_ids(args)
    if args.limit:
        ids = ids[:args.limit]
    checkin, checkout = args.checkin or default_stay()[0], args.checkout or default_stay()[1]
    cookies, visitor_id = load_cookies(args.locale, args.currency)
    print(f"Crawl chi tiết: {len(ids)} khách sạn | {args.locale}/{args.currency.upper()} | "
          f"nghỉ {args.delay}–{args.delay + args.jitter:.1f}s mỗi lượt")

    stopped = threading.Event()
    lock = threading.Lock()
    stats = {"done": 0, "failed": 0, "skipped": 0}
    blocked_reasons: list[str] = []
    client_options = {"cookies": cookies, "timeout": args.timeout, "http2": True}
    proxy = config.httpx_proxy_url()
    if proxy:
        client_options["proxy"] = proxy

    def one(index: int, hotel_id: str, client) -> None:
        if stopped.is_set():
            return
        old_dump = None if getattr(args, "force", False) else saved_raw(
            hotel_id, args.locale, args.currency)
        if old_dump is not None and raw_complete(old_dump):
            with lock:
                stats["skipped"] += 1
                print(f"  [{index}/{len(ids)}] {hotel_id} ĐÃ CÓ · bỏ qua (đủ chi tiết + lân cận)")
            return
        time.sleep(random.uniform(args.delay, args.delay + args.jitter))
        if stopped.is_set():
            return
        try:
            dump, reason = fetch_one(client, hotel_id, args.locale, args.currency,
                                     checkin, checkout, visitor_id)
            path = save(dump, hotel_id, args.locale, args.currency)
        except Exception as exc:
            with lock:
                stats["failed"] += 1
                print(f"  [{index}/{len(ids)}] {hotel_id} LỖI MẠNG | {exc}")
            return
        normalized = dump["normalized"]
        with lock:
            if reason:
                blocked_reasons.append(reason)
                stopped.set()
                print(f"  [{index}/{len(ids)}] {hotel_id} BỊ CHẶN | {reason}")
            elif normalized.get("success"):
                stats["done"] += 1
                print(f"  [{index}/{len(ids)}] {hotel_id} OK | "
                      f"mô tả={len(normalized.get('description') or '')} ký tự, "
                      f"chính sách={normalized.get('policy_count', 0)}, "
                      f"lân cận={normalized.get('nearby_count', 0)} → {path.name}")
            else:
                stats["failed"] += 1
                print(f"  [{index}/{len(ids)}] {hotel_id} THIẾU | {normalized.get('error')}")

    with httpx.Client(**client_options) as client:
        if args.concurrency == 1:
            for index, hotel_id in enumerate(ids, 1):
                one(index, hotel_id, client)
                if stopped.is_set():
                    break
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [pool.submit(one, index, hotel_id, client)
                           for index, hotel_id in enumerate(ids, 1)]
                for future in futures:
                    future.result()

    if blocked_reasons:
        print("Dừng lại: Trip.com đang chặn. Hãy nghỉ vài giờ hoặc lấy lại cookie; app không tự vượt chặn.")
        return 2
    print(f"Xong: {stats['done']} crawl mới, {stats['skipped']} đã có, {stats['failed']} hỏng.")
    return 0 if stats["done"] or stats["skipped"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hotel-id")
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--ids-file")
    parser.add_argument("--file")
    parser.add_argument("--locale", default="vi-VN")
    parser.add_argument("--currency", default="VND")
    parser.add_argument("--checkin")
    parser.add_argument("--checkout")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--jitter", type=float, default=1.5)
    parser.add_argument("--concurrency", type=int, default=1, choices=(1, 2, 3, 4))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--chi-dump", action="store_true")
    parser.add_argument("--force", action="store_true", help="crawl lại cả raw đã hoàn chỉnh")
    parser.add_argument("--into-raw", action="store_true")
    parser.add_argument("--export-cookies", action="store_true")
    parser.add_argument("--cookie-wait", type=int, default=45)
    raise SystemExit(main(parser.parse_args()))
