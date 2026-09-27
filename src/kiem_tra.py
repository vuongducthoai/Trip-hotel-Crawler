"""Kiểm tra sức khoẻ trước khi cào: cookie, profile, mạng, Trip.com có trả dữ liệu không.

Mỗi mục trả về {"ten", "trang_thai": "ok"|"warn"|"fail", "chi_tiet"}.
"fail" = không nên cào; "warn" = cào được nhưng có rủi ro.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config                                   # noqa: E402
from api_extract import extract_from_html         # noqa: E402
from crawl_fast import MARKET_HOST, cookie_file, headers_for  # noqa: E402

MARKETS = {"vi": ("vi-VN", "VND"), "en": ("en-US", "USD")}
COOKIE_MAX_AGE_H = 24
LOGIN_COOKIES = ("cticket", "login_uid", "login_type", "DUID")
PROBE_CITY = {"id": 58, "name": "Hồng Kông", "name_en": "Hong Kong", "province_id": 32,
              "country_id": 1, "country_name": "Trung Quốc", "country_name_en": "China"}


def _item(ten: str, trang_thai: str, chi_tiet: str, **extra) -> dict:
    return {"ten": ten, "trang_thai": trang_thai, "chi_tiet": chi_tiet, **extra}


def _read_cookies(locale: str, currency: str) -> dict | None:
    path = cookie_file(locale, currency)
    if not path.exists():
        return None
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        return {c["name"]: c["value"] for c in values if c.get("name")}
    except (OSError, ValueError):
        return {}


def kiem_tra_ngon_ngu(lang: str, city: dict | None = None, probe: bool = True) -> list[dict]:
    locale, currency = MARKETS[lang]
    tag = lang.upper()
    out: list[dict] = []

    # 1. Chrome profile
    profile = config.profile_dir(locale, currency)
    if profile.exists() and any(profile.iterdir()):
        out.append(_item(f"Chrome profile {tag}", "ok", f"Có tại {profile.name}"))
    else:
        out.append(_item(f"Chrome profile {tag}", "warn",
                         "Chưa có profile; lần cào đầu Chrome sẽ mở với phiên trống, dễ gặp captcha."))

    # 2. Cookie file (bước cào chi tiết cần)
    cookies = _read_cookies(locale, currency)
    if cookies is None:
        out.append(_item(f"Cookie {tag}", "warn",
                         "Chưa có file cookie — app sẽ tự mở Chrome ~45 giây để lấy khi tới bước chi tiết."))
    elif not cookies:
        out.append(_item(f"Cookie {tag}", "fail", "File cookie hỏng. Bấm 'Lấy lại cookie'."))
    else:
        age_h = (time.time() - cookie_file(locale, currency).stat().st_mtime) / 3600
        logged = any(k in cookies for k in LOGIN_COOKIES)
        if age_h > COOKIE_MAX_AGE_H:
            out.append(_item(f"Cookie {tag}", "warn",
                             f"Cookie đã {age_h / 24:.1f} ngày tuổi ({len(cookies)} cookie). Nên bấm 'Lấy lại cookie'."))
        else:
            out.append(_item(f"Cookie {tag}", "ok", f"{len(cookies)} cookie, lấy {age_h:.1f} giờ trước."))
        out.append(_item(f"Đăng nhập Trip.com {tag}", "ok" if logged else "warn",
                         "Profile đã đăng nhập." if logged
                         else "Chưa đăng nhập Trip.com trong profile — dễ bị giới hạn danh sách (ResultId=201)."))

    if not probe:
        return out

    # 3. Gọi thử trang danh sách (SSR) bằng httpx + cookie hiện có
    try:
        import httpx
    except ImportError:
        out.append(_item(f"Trip.com {tag}", "warn", "Thiếu thư viện httpx, bỏ qua kiểm tra mạng."))
        return out
    from crawl_api import build_list_url   # import muộn: crawl_api kéo theo playwright
    target = city or PROBE_CITY
    tomorrow = datetime.now() + timedelta(days=1)
    url = build_list_url(target, tomorrow.strftime("%Y-%m-%d"),
                         (tomorrow + timedelta(days=1)).strftime("%Y-%m-%d"), locale, currency)
    headers = headers_for(locale, currency)
    headers.pop("Content-Type", None)
    client_options = {"headers": headers, "cookies": cookies or {}, "timeout": 20.0,
                      "follow_redirects": True}
    proxy = config.httpx_proxy_url()
    if proxy:
        client_options["proxy"] = proxy
    t0 = time.time()
    try:
        with httpx.Client(**client_options) as client:
            resp = client.get(url)
    except Exception as exc:
        out.append(_item(f"Trip.com {tag}", "fail",
                         f"Không kết nối được {MARKET_HOST.get(locale)}: {type(exc).__name__}. Kiểm tra mạng/VPN/proxy."))
        return out
    ms = int((time.time() - t0) * 1000)
    html = resp.text
    low = html.lower()
    if resp.status_code != 200:
        out.append(_item(f"Trip.com {tag}", "fail", f"HTTP {resp.status_code} khi mở trang danh sách ({ms} ms)."))
        return out
    if any(m.lower() in low for m in ("c-slide-captcha", "challenge_page", "antibot", "/account/signin")):
        out.append(_item(f"Trip.com {tag}", "fail",
                         "Trip.com đang yêu cầu captcha/đăng nhập cho IP này. Nghỉ vài giờ hoặc đăng nhập profile rồi thử lại."))
        return out
    rows, meta = extract_from_html(html, city_name=target.get("name"))
    total = meta.get("total")
    if rows:
        out.append(_item(f"Trip.com {tag}", "ok",
                         f"Trang danh sách trả {len(rows)} khách sạn SSR (cả thành phố {total}) sau {ms} ms.",
                         so_ssr=len(rows), tong=total))
    else:
        out.append(_item(f"Trip.com {tag}", "warn",
                         f"Trang mở được ({ms} ms) nhưng không có khách sạn SSR — có thể bị giới hạn mềm; app vẫn thử bằng Chrome."))
    return out


def kiem_tra(languages: list[str], city: dict | None = None, probe: bool = True) -> dict:
    items: list[dict] = []
    for lang in languages:
        if lang in MARKETS:
            items.extend(kiem_tra_ngon_ngu(lang, city, probe))
    worst = "ok"
    if any(i["trang_thai"] == "fail" for i in items):
        worst = "fail"
    elif any(i["trang_thai"] == "warn" for i in items):
        worst = "warn"
    return {"ket_luan": worst, "muc": items, "luc": datetime.now().isoformat(timespec="seconds")}


if __name__ == "__main__":
    print(json.dumps(kiem_tra(sys.argv[1:] or ["vi"]), ensure_ascii=False, indent=2))
