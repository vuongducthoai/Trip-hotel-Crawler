"""Bước 3 (đường A) — crawl danh sách khách sạn qua API phân trang thật.

Lịch sử điều tra (xem docs/recon.md):
  - `fetchDynamicRefreshList` chỉ làm mới card đã hiện, không phải nguồn danh sách.
  - Trang 1 nằm sẵn trong HTML (SSR, Next.js `self.__next_f.push`).
  - Trang 2 trở đi gọi `POST /restapi/soa2/34951/fetchHotelList` với
    body chứa `paging.pageIndex` + `hotelIdFilter.hotelAldyShown`.
  - Cuộn chỉ kéo được vài chục khách sạn rồi trang tự báo hết (isLastPage).
    Nên KHÔNG cuộn để lấy hết nữa: cuộn 1-2 vòng chỉ để BẮT MẪU request
    (kèm token chống bot do chính trang sinh ra), rồi phát lại request đó
    ngay TRONG trang, tăng dần pageIndex.
  - Nếu Trip.com cắt mềm danh sách, crawler giữ checkpoint và báo rõ; không
    chia truy vấn theo dữ liệu ngoài phạm vi hoặc tìm cách vượt giới hạn.

    python src/crawl_api.py                       # chạy hết VN_CITIES
    python src/crawl_api.py --city-id 301
    python src/crawl_api.py --city "Đà Nẵng"
    python src/crawl_api.py --city-id 301 --max-pages 5    # chạy thử nhanh

Kết quả: output/data/api_hotels_<cityId>_<timestamp>.json
File được ghi lại sau mỗi 20 trang (checkpoint) nên đứt giữa chừng
vẫn còn dữ liệu, không mất trắng. Con số "tổng KS" Trip.com tự báo có dao
động nhẹ giữa các lần gọi (quan sát được ±5-8%) — coi tỉ lệ % cuối log là
ước lượng, không phải con số tuyệt đối.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

import config
from api_extract import (
    dedupe,
    extract_from_html,
    extract_next_object,
    find_hotel_lists,
    is_last_page,
    parse_hotel,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NOISE = re.compile(r"(google|gstatic|doubleclick|facebook|sentry|/log|/track|bee/collect)", re.I)
HOTEL_SERVICE = "/restapi/soa2/34951/"
LIST_ENDPOINT = "fetchHotelList"
RECOMMEND_ENDPOINT = "fetchRecommendList"
LIST_ENDPOINTS = (LIST_ENDPOINT, RECOMMEND_ENDPOINT)

# fetch() của trình duyệt tự quản lý các header này, truyền vào sẽ bị bỏ
# qua hoặc báo lỗi — phải lọc ra khỏi mẫu bắt được.
FORBIDDEN_HEADERS = {
    "host", "connection", "content-length", "cookie", "cookie2", "date",
    "accept-encoding", "accept-charset", "origin", "referer", "te", "trailer",
    "transfer-encoding", "upgrade", "via", "expect", "dnt", "keep-alive",
}


def market_host(locale: str) -> str:
    return "www.trip.com" if locale.lower().startswith("en") else "vn.trip.com"


def city_name_for_locale(city: dict, locale: str) -> str:
    return (city.get("name_en") or city["name"]) if locale.lower().startswith("en") else city["name"]


def build_list_url(
    city: dict, checkin: str, checkout: str,
    locale: str = "vi-VN", currency: str = "VND",
) -> str:
    """Dựng thẳng URL trang danh sách, khỏi phải gõ ô tìm kiếm + click gợi ý."""
    name = city_name_for_locale(city, locale)
    # Thành phố nước ngoài mang theo mã + tên quốc gia riêng (xem --country-id);
    # thành phố VN giữ nguyên như cũ.
    english = locale.lower().startswith("en")
    country_name = (city.get("country_name_en") if english else city.get("country_name")) \
        or city.get("country_name_en") or ("Vietnam" if english else "Việt Nam")
    params = {
        "flexType": "1",
        "cityId": str(city["id"]),
        "provinceId": str(city.get("province_id") or 0),
        "districtId": "0",
        "countryId": str(city.get("country_id") or 111),
        "cityName": name,
        "destName": f"{name}, {country_name}",
        "searchWord": name,
        "searchType": "CT",
        "optionId": str(city["id"]),
        "searchValue": f"19|{city['id']}*19*{city['id']}",
        "checkin": checkin,
        "checkout": checkout,
        "crn": "1",
        "adult": "2",
        "curr": currency.upper(),
        "locale": locale,
        "old": "1",
    }
    return f"https://{market_host(locale)}/hotels/list?" + urllib.parse.urlencode(
        params, quote_via=urllib.parse.quote
    )


class HotelCollector:
    """Nghe response JSON, thu khách sạn VÀ bắt mẫu request phân trang."""

    def __init__(self, city_name: str) -> None:
        self.city_name = city_name
        self.rows: list[dict] = []
        self.last_page_seen = False
        self.hotel_service_calls = 0
        self.list_service_calls = 0
        self.empty_list_service_calls = 0
        self.last_empty_list_status: dict = {}
        self.sources: dict[str, int] = {}
        self.template: dict | None = None     # mẫu request fetchHotelList
        self.empty_template: dict | None = None  # request thật nhưng response chưa có data
        self.dump_dir = config.RECON_DIR / "after_search"
        self.dump_dir.mkdir(parents=True, exist_ok=True)
        self._dumped: set[str] = set()

    async def on_response(self, resp) -> None:
        req = resp.request
        if req.resource_type not in ("xhr", "fetch") or NOISE.search(req.url):
            return
        try:
            body = await resp.json()
        except Exception:
            return

        if HOTEL_SERVICE in req.url:
            self.hotel_service_calls += 1
            self._dump_once(req, body)

        # Bắt mẫu request phân trang — chỉ cần 1 lần, có token là dùng lại được.
        endpoint_path = req.url.split("?", 1)[0]
        endpoint_name = next(
            (name for name in LIST_ENDPOINTS if endpoint_path.endswith(f"/{name}")),
            None,
        )
        is_list = endpoint_name is not None
        if is_list:
            self.list_service_calls += 1
        current_name = (self.template or {}).get("endpoint")
        prefer_template = (
            self.template is None
            or (endpoint_name == LIST_ENDPOINT and current_name != LIST_ENDPOINT)
        )
        # Không nhận một request chỉ trả ResponseStatus làm mẫu phân trang.
        # Một số phiên tự gọi page 2 quá sớm và server trả 200 nhưng không có
        # `data`; nếu giữ mẫu này thì crawler phát lại hàng trăm request rỗng.
        usable_list_response = isinstance(body.get("data"), dict) and bool(body.get("data"))
        if is_list and not usable_list_response:
            self.empty_list_service_calls += 1
            self.last_empty_list_status = body.get("ResponseStatus") or {}
        fallback_name = (self.empty_template or {}).get("endpoint")
        prefer_fallback = (
            self.empty_template is None
            or (endpoint_name == LIST_ENDPOINT and fallback_name != LIST_ENDPOINT)
        )
        if is_list and req.post_data and (
            (usable_list_response and prefer_template)
            or (not usable_list_response and prefer_fallback)
        ):
            try:
                headers = await req.all_headers()
            except Exception:
                headers = req.headers
            captured_template = {
                "url": req.url,
                "headers": {
                    k: v for k, v in headers.items()
                    if not k.startswith(":") and k.lower() not in FORBIDDEN_HEADERS
                },
                "post_data": req.post_data,
                "endpoint": endpoint_name,
            }
            if usable_list_response:
                self.template = captured_template
            else:
                self.empty_template = captured_template

        hits = find_hotel_lists(body)
        if hits:
            endpoint = req.url.split("?")[0]
            got = 0
            for _, arr in hits:
                for entry in arr:
                    row = parse_hotel(entry, self.city_name)
                    if row:
                        self.rows.append(row)
                        got += 1
            if got:
                self.sources[endpoint] = self.sources.get(endpoint, 0) + got

        # CHỈ tin isLastPage từ đúng endpoint danh sách. Trước đây tin cả
        # response khác nên dừng oan ở 49 KS trong khi thành phố có 6546.
        if is_list and is_last_page(body):
            self.last_page_seen = True

    def _dump_once(self, req, body) -> None:
        endpoint = req.url.split("?")[0]
        if endpoint in self._dumped:
            return
        self._dumped.add(endpoint)
        name = re.sub(r"[^A-Za-z0-9._-]", "_", endpoint)[-80:]
        (self.dump_dir / f"{name}.json").write_text(
            json.dumps(
                {"url": req.url, "post_data": req.post_data, "response": body},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )


SCROLL_TO_BOTTOM_JS = "window.scrollTo(0, document.body.scrollHeight); document.body.scrollHeight"

# Phát lại request NGAY TRONG trang: cookie, service worker và mọi lớp
# chống bot của trang đều tự áp dụng, giống hệt lúc trang tự gọi.
PAGE_FETCH_JS = """
async ({url, headers, body}) => {
  try {
    const r = await fetch(url, {
      method: 'POST', headers, body,
      credentials: 'include', mode: 'cors',
    });
    return {status: r.status, text: await r.text()};
  } catch (e) {
    return {status: -1, text: String(e)};
  }
}
"""


def _apply_extra(filters: list[dict], extra: list[dict]) -> list[dict]:
    """Thay/thêm filter theo type — dùng cho cả probe lẫn crawl thật."""
    types = {e["type"] for e in extra}
    return [dict(f) for f in filters if f.get("type") not in types] + list(extra)


def _fmt_extra(extra: list[dict] | None) -> str:
    if not extra:
        return "(toàn bộ)"
    return "+".join(f"{e['type']}={e['value']}" for e in extra)


def _response_status_text(payload: dict) -> str:
    """Tóm tắt phản hồi rỗng để biết Trip.com không cung cấp dữ liệu danh sách."""
    status = payload.get("ResponseStatus") or {}
    extensions = status.get("Extension") or []
    result_id = next(
        (item.get("value") or item.get("Value") for item in extensions
         if str(item.get("id") or item.get("Id")).lower() == "resultid"),
        None,
    )
    suffix = f", ResultId={result_id}" if result_id else ""
    return f"Ack={status.get('Ack')}, Errors={str(status.get('Errors'))[:200]}{suffix}"


async def probe_count(page, tpl: dict, base_filters: list[dict], extra: list[dict]) -> int | None:
    """1 request pageSize=1 → hotelTotalCount server báo cho tổ hợp filter này."""
    body = json.loads(tpl["post_data"])
    body["filters"] = _apply_extra(base_filters, extra)
    body["paging"] = {**body.get("paging", {}), "pageIndex": 1, "pageSize": 1}
    body["hotelIdFilter"] = {"hotelAldyShown": []}
    res = await page.evaluate(
        PAGE_FETCH_JS,
        {"url": tpl["url"], "headers": tpl["headers"], "body": json.dumps(body, ensure_ascii=False)},
    )
    if res["status"] != 200:
        print(f"    ! Probe {_fmt_extra(extra)}: HTTP {res['status']} — {res['text'][:300]}")
        return None
    try:
        payload = json.loads(res["text"])
    except Exception:
        print(f"    ! Probe {_fmt_extra(extra)}: response không phải JSON — {res['text'][:300]}")
        return None
    count = ((payload.get("data") or {}).get("hotelListAddtionInfo") or {}).get("hotelTotalCount")
    if count is None:
        print(f"    ! Probe {_fmt_extra(extra)} không có hotelTotalCount; "
              f"top-level keys={list(payload)[:10]}")
        print(f"      ResponseStatus: {_response_status_text(payload)}")
    return count


def _save(
    city: dict, rows: list[dict], out: Path, done: bool, total,
    locale: str, currency: str,
) -> None:
    captured = datetime.now()
    out.write_text(
        json.dumps(
            {
                "source": LIST_ENDPOINT,
                "city_id": city["id"],
                "city_name": city_name_for_locale(city, locale),
                "locale": locale,
                "currency": currency,
                "check_in": (captured + timedelta(days=1)).strftime("%Y-%m-%d"),
                "check_out": (captured + timedelta(days=2)).strftime("%Y-%m-%d"),
                "crawled_at": captured.isoformat(timespec="seconds"),
                "city_total_reported": total,
                "complete": done,
                "count": len(rows),
                "hotels": rows,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


async def paginate(
    page, collector, city: dict, out: Path, total, max_pages: int,
    extra_filters: list[dict] | None = None, seen: set[str] | None = None,
    locale: str = "vi-VN", currency: str = "VND",
) -> set[str]:
    """Phát lại fetchHotelList, tăng dần pageIndex cho tới khi hết.

    `extra_filters` là bộ lọc đã có sẵn trong request. `seen` là tập mã đã thấy
    để chống trùng giữa các trang. Hàm trả lại `seen` sau khi cập nhật.
    """
    tpl = collector.template
    body = json.loads(tpl["post_data"])
    if extra_filters:
        body["filters"] = _apply_extra(body.get("filters", []), extra_filters)
    paging = body.setdefault("paging", {})
    orig_size = paging.get("pageSize") or 10
    paging["pageSize"] = config.API_PAGE_SIZE
    # Mảnh riêng (có extra_filters) không có trang 1 SSR tương ứng — phải
    # bắt đầu lại từ trang 1, không tiếp nối pageIndex của request mẫu gốc.
    page_index = 0 if extra_filters else int(paging.get("pageIndex") or 1)

    if seen is None:
        seen = {r["trip_hotel_id"] for r in collector.rows}
    # Chỉ gửi ID đã thấy trong chính mảnh hiện tại. Gửi ID của mọi mảnh trước
    # làm hotelAldyShown khiến trạng thái phân trang phía server bị nhiễu.
    leaf_seen_ids: list[str] = []
    leaf_seen_set: set[str] = set()
    empty_streak = 0
    size_fallback_done = False
    label = _fmt_extra(extra_filters)

    print(f"  • {label}: gọi API phân trang (pageSize={config.API_PAGE_SIZE}, "
          f"tối đa {max_pages} trang)…")

    n = 0
    while n < max_pages:
        n += 1
        page_index += 1
        paging["pageIndex"] = page_index
        # Server dùng TOÀN BỘ danh sách này để loại các card đã trả. Chỉ giữ
        # 300 ID làm server quay vòng kết quả sau khoảng 800 khách sạn.
        body.setdefault("hotelIdFilter", {})["hotelAldyShown"] = leaf_seen_ids

        res = await page.evaluate(
            PAGE_FETCH_JS,
            {"url": tpl["url"], "headers": tpl["headers"],
             "body": json.dumps(body, ensure_ascii=False)},
        )

        if res["status"] != 200:
            print(f"    ! Trang {page_index}: HTTP {res['status']}. Dừng lại.")
            (collector.dump_dir / f"fail_page_{page_index}.txt").write_text(
                res["text"][:20000], encoding="utf-8")
            break

        try:
            payload = json.loads(res["text"])
        except Exception:
            print(f"    ! Trang {page_index}: response không phải JSON. Dừng lại.")
            (collector.dump_dir / f"fail_page_{page_index}.txt").write_text(
                res["text"][:20000], encoding="utf-8")
            break

        entries = ((payload.get("data") or {}).get("hotelList")) or []
        if not entries and not isinstance(payload.get("data"), dict):
            print(
                f"    ! Trang {page_index}: Trip.com trả phản hồi danh sách rỗng "
                f"({_response_status_text(payload)})."
            )
        new = 0
        leaf_new = 0
        for entry in entries:
            row = parse_hotel(entry, city_name_for_locale(city, locale))
            if not row:
                continue
            hid = row["trip_hotel_id"]
            if hid not in leaf_seen_set:
                leaf_seen_set.add(hid)
                leaf_seen_ids.append(hid)
                leaf_new += 1
            if hid not in seen:
                seen.add(hid)
                collector.rows.append(row)
                new += 1

        # pageSize lớn không được chấp nhận → lùi về giá trị gốc, thử lại.
        # CHỈ xét ở lượt đầu: trang rỗng ở giữa chừng là do hết KS thật,
        # lùi pageSize lúc đó chỉ tốn thêm một lượt gọi vô ích.
        if not entries and n == 1 and not size_fallback_done and config.API_PAGE_SIZE != orig_size:
            size_fallback_done = True
            paging["pageSize"] = orig_size
            page_index -= 1
            n -= 1  # đổi pageSize không làm mất một trang trong --max-pages
            print(f"    · pageSize={config.API_PAGE_SIZE} không có kết quả, "
                  f"lùi về {orig_size} và thử lại.")
            continue

        leaf_seen = len(leaf_seen_set)
        # Một bucket có thể chồng bucket trước. Chỉ dừng khi API lặp trong
        # chính bucket này, không dừng vì bản ghi đã tồn tại ở bucket khác.
        empty_streak = empty_streak + 1 if leaf_new == 0 else 0
        # In dày ở đầu để thấy ngay là chạy được, sau đó thưa lại cho đỡ rối.
        if n <= 5 or n % 10 == 0 or new == 0:
            pct = f" ({leaf_seen * 100 // total}% của mảnh này)" if total else ""
            overlap = f", +{leaf_new} trong mảnh" if leaf_new != new else ""
            print(f"    trang {page_index}: +{new} mới{overlap} → {leaf_seen}/{total}{pct}"
                  f" | tổng gộp toàn thành phố: {len(seen)}")

        if n % config.CHECKPOINT_EVERY == 0:
            _save(city, dedupe(collector.rows), out, False, total, locale, currency)

        if is_last_page(payload):
            if total and leaf_seen < total * 0.90:
                print(f"    · Server báo hết sớm ở trang {page_index} "
                      f"({leaf_seen}/{total}); tiếp tục kiểm chứng.")
            else:
                print(f"    · Server báo hết trang ở trang {page_index}.")
                break
        if empty_streak >= 3:
            print("    · 3 trang liền không có KS mới — coi như hết.")
            break
        if total and leaf_seen >= total:
            break

        await asyncio.sleep(random.uniform(config.API_MIN_DELAY, config.API_MAX_DELAY))

    return seen


async def crawl_one_city(
    ctx, city: dict, out: Path, max_pages: int, allow_recommend: bool = False,
    target_count: int | None = None, locale: str = "vi-VN", currency: str = "VND",
) -> tuple[list[dict], int | None, bool]:
    page = await ctx.new_page()
    localized_city_name = city_name_for_locale(city, locale)
    collector = HotelCollector(localized_city_name)
    page.on("response", lambda r: asyncio.create_task(collector.on_response(r)))

    tomorrow = datetime.now() + timedelta(days=1)
    day_after = tomorrow + timedelta(days=1)
    url = build_list_url(
        city, tomorrow.strftime("%Y-%m-%d"), day_after.strftime("%Y-%m-%d"),
        locale, currency,
    )

    print(f"\n=== {localized_city_name} (cityId={city['id']}, {locale}/{currency}) ===")
    await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    await page.wait_for_timeout(4000)

    # --- Trang 1: nằm sẵn trong HTML (SSR), không đi qua API ---
    html = await page.content()
    market_tag = f"{locale}_{currency}".replace("-", "")
    html_path = config.HTML_DIR / f"list_{city['id']}_{market_tag}.html"
    html_path.write_text(html, encoding="utf-8")
    ssr_rows, meta = extract_from_html(html, city_name=localized_city_name)
    total = meta.get("total")
    if ssr_rows:
        collector.rows.extend(ssr_rows)
        print(f"  • HTML (trang 1): {len(ssr_rows)} khách sạn | cả thành phố: {total}")
    else:
        print(f"  ! Không bóc được dữ liệu từ HTML — xem {html_path}")

    # Để chính trang tải thêm card trước. Cách này dùng request thật do trang tạo,
    # phù hợp hơn việc phát lại API khi Trip.com thay token hoặc cấu trúc phiên.
    for round_index in range(config.MAX_SCROLL_ROUNDS):
        current = len(dedupe(collector.rows))
        if target_count and current >= target_count:
            break
        try:
            await page.evaluate(SCROLL_TO_BOTTOM_JS)
        except Exception:
            break
        await page.wait_for_timeout(config.SCROLL_PAUSE_MS)
        updated = len(dedupe(collector.rows))
        if updated > current:
            print(f"  • Cuộn {round_index + 1}: +{updated - current} → {updated} khách sạn")
        if collector.last_page_seen and updated == current:
            break

    # Với một số AB test, vào URL trực tiếp chỉ trả danh sách SEO rút gọn và
    # cuộn không phát request. Click nút Tìm để frontend tự tạo token/request
    # đầy đủ giống thao tác người dùng thật.
    if not collector.template and collector.empty_list_service_calls:
        status_payload = {"ResponseStatus": collector.last_empty_list_status}
        print(
            "  ⚠ Trang đã tự gọi API danh sách nhưng Trip.com trả phản hồi rỗng "
            f"({_response_status_text(status_payload)})."
        )
        print("    Không bấm Tìm lần nữa để tránh danh sách đang hiện bị đổi thành 0.")
        if collector.empty_template:
            collector.template = collector.empty_template
            print("  • Thử lại bằng request thật và toàn bộ header do Chrome vừa tạo.")
    elif not collector.template:
        try:
            button_name = "Search" if locale.lower().startswith("en") else "Tìm"
            search_button = page.get_by_role("button", name=button_name, exact=True)
            if await search_button.count():
                print("  • Chưa có mẫu API — kích hoạt nút Tìm trên trang…")
                await search_button.first.click()
                await page.wait_for_timeout(5000)
                for _ in range(5):
                    if collector.template:
                        break
                    await page.evaluate(SCROLL_TO_BOTTOM_JS)
                    await page.wait_for_timeout(config.SCROLL_PAUSE_MS)
                html = await page.content()
                html_path.write_text(html, encoding="utf-8")
        except Exception as e:
            print(f"    ! Không kích hoạt được nút Tìm: {e}")

    # Một số phiên/AB test render card nhưng không phát fetchHotelList ở
    # browser. Khi đó Next.js vẫn nhúng body chuẩn trong initListRequest.
    if not collector.template:
        init_request = extract_next_object(html, "initListRequest")
        if init_request:
            init_request.setdefault("head", {})["isSSR"] = False
            collector.template = {
                "url": f"https://{market_host(locale)}{HOTEL_SERVICE}{LIST_ENDPOINT}",
                "headers": {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                },
                "post_data": json.dumps(init_request, ensure_ascii=False),
                "endpoint": LIST_ENDPOINT,
            }
            print("  • Dùng initListRequest trong HTML làm mẫu API.")

    expected_total = total
    collected = len(dedupe(collector.rows))
    if collector.template and (not target_count or collected < target_count):
        tpl = collector.template
        if tpl.get("endpoint") == RECOMMEND_ENDPOINT and not allow_recommend:
            await page.close()
            raise SystemExit(
                "Trip.com đang dùng fetchRecommendList (tập gợi ý rút gọn), không phải "
                "fetchHotelList đầy đủ. Browser profile hiện có khả năng đã đăng xuất.\n"
                "→ Chạy: python src/setup_profile.py\n"
                "→ Đăng nhập Trip.com, tìm thử TP.HCM, rồi đóng Chromium và chạy lại.\n"
                "Nếu chủ ý chỉ lấy tập rút gọn, thêm --allow-recommend."
            )
        base_filters = json.loads(tpl["post_data"]).get("filters", [])
        baseline = await probe_count(page, tpl, base_filters, [])
        list_blocked = baseline is None and collector.empty_list_service_calls > 0
        baseline = baseline or total
        known_totals = [x for x in (baseline, total) if x is not None]
        expected_total = max(known_totals) if known_totals else None

        if list_blocked:
            print(
                "  ⛔ Trip.com đang giới hạn API danh sách (ResultId=201); "
                "dừng để không gửi thêm request vô ích."
            )
            print("    Dữ liệu đã có và checkpoint cũ vẫn được giữ nguyên.")
            seen = {row["trip_hotel_id"] for row in dedupe(collector.rows)}
        else:
            seen = await paginate(
                page, collector, city, out, baseline, max_pages,
                locale=locale, currency=currency,
            )
        if target_count and len(seen) < target_count:
            print(f"  ⚠ Trip.com chỉ trả {len(seen)}/{target_count} khách sạn. "
                  "Giữ checkpoint và dừng, không chia truy vấn theo giá hay thử vượt chặn mềm.")
    elif not collector.template and (not target_count or collected < target_count):
        print("  ⚠ Không bắt được mẫu request fetchHotelList sau 8 vòng cuộn.")
        print(f"    Xem {collector.dump_dir} và ảnh chụp bên dưới rồi gửi lại cho em.")
        await page.screenshot(path=str(config.HTML_DIR / f"debug_{city['id']}_notpl.png"))

        expected_total = total

    result = dedupe(collector.rows)
    complete = (
        len(result) >= target_count if target_count
        else bool(expected_total and len(result) >= expected_total * config.MIN_COMPLETE_RATIO)
    )
    pct = f" ({len(result) * 100 // expected_total}% của {expected_total})" if expected_total else ""
    print(f"  → {len(result)} khách sạn duy nhất{pct}")
    if expected_total and not complete:
            print(f"  ⚠ Chưa đạt ngưỡng hoàn chỉnh {config.MIN_COMPLETE_RATIO:.0%}; "
              "file checkpoint được giữ với complete=false.")
    await page.close()
    return result, expected_total, complete


async def main(args: argparse.Namespace) -> None:
    locale = args.locale or config.LOCALE
    currency = (args.currency or config.CURRENCY).upper()
    cities = config.VN_CITIES
    if args.city_id and args.city_name:
        # Thành phố ngoài danh sách VN (vd Copenhagen): tự dựng từ tham số.
        cities = [{
            "id": args.city_id, "name": args.city_name, "name_en": args.city_name,
            "province_id": args.province_id,
            "country_id": args.country_id, "country_name": args.country_name,
            "country_name_en": args.country_name,
        }]
    elif args.city_id:
        cities = [c for c in cities if c["id"] == args.city_id]
    elif args.city:
        cities = [c for c in cities if args.city.lower() in c["name"].lower()]
    if not cities:
        raise SystemExit("Không khớp thành phố nào trong config.VN_CITIES. "
                         "Thành phố nước ngoài: thêm --city-name, --country-id, --country-name.")

    max_pages = args.max_pages or config.MAX_API_PAGES
    profile_path = Path(args.profile_dir) if args.profile_dir else config.profile_dir(locale, currency)
    if not profile_path.is_absolute():
        profile_path = config.ROOT / profile_path
    print(f"  • Chrome profile: {profile_path}")

    async with async_playwright() as p:
        launch_options = dict(
            user_data_dir=str(profile_path),
            channel="chrome",
            headless=config.HEADLESS,
            locale=locale,
            timezone_id=config.TIMEZONE,
            viewport=config.VIEWPORT,
            # Một số mạng/ISP làm HTTP/3 của Chrome lỗi ERR_QUIC_PROTOCOL_ERROR.
            # Tắt QUIC để Chrome dùng HTTPS qua TCP; không thay fingerprint hay vượt chặn.
            args=["--disable-quic"],
        )
        proxy = config.browser_proxy()
        if proxy:
            launch_options["proxy"] = proxy
        ctx = await p.chromium.launch_persistent_context(**launch_options)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        market_tag = f"{locale}_{currency}".replace("-", "")
        for i, city in enumerate(cities):
            out = config.DATA_DIR / f"api_hotels_{city['id']}_{market_tag}_{stamp}.json"
            rows, expected_total, complete = await crawl_one_city(
                ctx, city, out, max_pages,
                allow_recommend=args.allow_recommend,
                target_count=args.target_count or args.limit,
                locale=locale,
                currency=currency,
            )
            if rows:
                if args.limit:
                    rows = rows[:args.limit]
                    complete = len(rows) == args.limit
                _save(city, rows, out, complete, expected_total, locale, currency)
                print(f"  → lưu {out}")

            if i < len(cities) - 1:
                await asyncio.sleep(random.uniform(config.MIN_DELAY * 2, config.MAX_DELAY * 2))

        await ctx.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", help="lọc theo tên (khớp một phần, không phân biệt hoa thường)")
    ap.add_argument("--city-id", type=int, help="chỉ chạy đúng 1 cityId")
    ap.add_argument("--city-name", help="tên thành phố ngoài VN_CITIES, dùng kèm --city-id (vd Copenhagen)")
    ap.add_argument("--province-id", type=int, default=0, help="mã tỉnh/khu vực Trip.com lấy từ URL trang danh sách")
    ap.add_argument("--country-id", type=int, help="mã quốc gia Trip.com của thành phố đó (lấy từ URL trang danh sách)")
    ap.add_argument("--country-name", help="tên quốc gia, vd Denmark")
    ap.add_argument("--max-pages", type=int, help="giới hạn số trang API (chạy thử nhanh)")
    ap.add_argument("--locale", default=config.LOCALE, help="Trip.com locale, ví dụ vi-VN hoặc en-US")
    ap.add_argument("--currency", default=config.CURRENCY, help="Mã tiền tệ, ví dụ VND hoặc USD")
    ap.add_argument("--limit", type=int, help="chỉ giữ tối đa N khách sạn trong file output mẫu")
    ap.add_argument("--profile-dir", help="profile Chromium tùy chọn; mặc định tách theo market")
    ap.add_argument(
        "--allow-recommend", action="store_true",
        help="cho phép crawl fetchRecommendList rút gọn khi profile đang đăng xuất",
    )
    ap.add_argument(
        "--target-count", type=int,
        help="dừng khi đạt số trip_hotel_id duy nhất này (vd 6000)",
    )
    args = ap.parse_args()
    if args.city_name and not (args.city_id and args.country_id and args.country_name):
        ap.error("--city-name cần đi kèm --city-id, --country-id và --country-name")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main(args))
