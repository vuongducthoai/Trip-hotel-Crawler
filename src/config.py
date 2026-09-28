"""Cấu hình chung của ứng dụng crawl Trip.com, không dùng cơ sở dữ liệu."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

# Khi đóng gói Electron, dữ liệu được ghi vào thư mục userData có quyền ghi.
DATA_ROOT = Path(os.getenv("TOOL_CRAWLER_DATA_DIR", str(ROOT))).resolve()
OUTPUT_DIR = DATA_ROOT / "output"
RECON_DIR = OUTPUT_DIR / "recon"
HTML_DIR = OUTPUT_DIR / "html"
DATA_DIR = OUTPUT_DIR / "data"
PROFILE_DIR = DATA_ROOT / "browser_profile"
for _folder in (OUTPUT_DIR, RECON_DIR, HTML_DIR, DATA_DIR):
    _folder.mkdir(parents=True, exist_ok=True)

HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
LOCALE = os.getenv("LOCALE", "vi-VN")
CURRENCY = os.getenv("CURRENCY", "VND")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh")
VIEWPORT = {"width": 1440, "height": 900}
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "60000"))

MIN_DELAY = float(os.getenv("MIN_DELAY", "1.5"))
MAX_DELAY = float(os.getenv("MAX_DELAY", "3.5"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "1"))
MAX_SCROLL_ROUNDS = int(os.getenv("MAX_SCROLL_ROUNDS", "25"))
SCROLL_PAUSE_MS = int(os.getenv("SCROLL_PAUSE_MS", "1500"))
MAX_API_PAGES = int(os.getenv("MAX_API_PAGES", "400"))
API_PAGE_SIZE = int(os.getenv("API_PAGE_SIZE", "20"))
API_MIN_DELAY = float(os.getenv("API_MIN_DELAY", "0.8"))
API_MAX_DELAY = float(os.getenv("API_MAX_DELAY", "1.8"))
CHECKPOINT_EVERY = int(os.getenv("CHECKPOINT_EVERY", "20"))
MIN_COMPLETE_RATIO = float(os.getenv("MIN_COMPLETE_RATIO", "0.98"))
# Gom trang 1 SSR theo nhiều tổ hợp bộ lọc (sao × điểm × sắp xếp) khi API
# danh sách bị chặn mềm (ResultId=201). Mỗi tổ hợp là 1 lần tải trang, ~12 KS.
SSR_SPLIT_ENABLED = os.getenv("SSR_SPLIT_ENABLED", "true").lower() == "true"
SSR_SPLIT_MIN_DELAY = float(os.getenv("SSR_SPLIT_MIN_DELAY", "1.2"))
SSR_SPLIT_MAX_DELAY = float(os.getenv("SSR_SPLIT_MAX_DELAY", "2.5"))
SSR_SPLIT_MAX_VARIANTS = int(os.getenv("SSR_SPLIT_MAX_VARIANTS", "120"))
SSR_SPLIT_STOP_AFTER_EMPTY = int(os.getenv("SSR_SPLIT_STOP_AFTER_EMPTY", "12"))
RESPECT_ROBOTS = os.getenv("RESPECT_ROBOTS", "true").lower() == "true"

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

import destinations

CORE_VN_CITIES: list[dict] = [
    {"id": 301, "name": "TP. Hồ Chí Minh", "name_en": "Ho Chi Minh City", "country_id": 111},
    {"id": 286, "name": "Hà Nội", "name_en": "Hanoi", "country_id": 111},
    {"id": 1356, "name": "Đà Nẵng", "name_en": "Da Nang", "country_id": 111},
    {"id": 1777, "name": "Nha Trang", "name_en": "Nha Trang", "country_id": 111},
    {"id": 5204, "name": "Đà Lạt", "name_en": "Dalat", "country_id": 111},
    {"id": 4134, "name": "Phan Thiết", "name_en": "Phan Thiet", "country_id": 111},
    {"id": 5649, "name": "Đảo Phú Quốc", "name_en": "Phu Quoc Island", "country_id": 111},
]

VN_CITIES: list[dict] = CORE_VN_CITIES + destinations.all_cities()


def _parse_proxy_line(line: str) -> tuple[str, str, str]:
    """Đọc proxy dạng host:port:user:pass hoặc URL đầy đủ."""
    line = line.strip()
    if "://" in line or "@" in line:
        from urllib.parse import unquote, urlsplit
        parsed = urlsplit(line if "://" in line else f"http://{line}")
        return (f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                unquote(parsed.username or ""), unquote(parsed.password or ""))
    parts = line.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}", "", ""
    if len(parts) >= 4:
        return f"http://{parts[0]}:{parts[1]}", parts[2], ":".join(parts[3:])
    raise ValueError("TRIP_PROXY không đúng định dạng host:port:user:pass.")


def browser_proxy() -> dict[str, str] | None:
    if os.getenv("TRIP_PROXY_ENABLED", "false").lower() != "true":
        return None
    line = os.getenv("TRIP_PROXY", "").strip()
    if line:
        server, username, password = _parse_proxy_line(line)
    else:
        server = os.getenv("TRIP_PROXY_SERVER", "").strip()
        username = os.getenv("TRIP_PROXY_USERNAME", "").strip()
        password = os.getenv("TRIP_PROXY_PASSWORD", "").strip()
    if not server:
        return None
    if bool(username) != bool(password):
        raise ValueError("Tên và mật khẩu proxy phải được điền cùng nhau.")
    result = {"server": server if "://" in server else f"http://{server}"}
    if username:
        result.update(username=username, password=password)
    return result


def httpx_proxy_url() -> str | None:
    proxy = browser_proxy()
    if not proxy:
        return None
    if not proxy.get("username"):
        return proxy["server"]
    from urllib.parse import quote, urlsplit, urlunsplit
    parsed = urlsplit(proxy["server"])
    auth = f"{quote(proxy['username'], safe='')}:{quote(proxy.get('password', ''), safe='')}@"
    return urlunsplit((parsed.scheme, auth + parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def profile_dir(locale: str, currency: str) -> Path:
    market = f"{locale}_{currency.upper()}".replace("/", "_").replace("\\", "_")
    return DATA_ROOT / f"browser_profile_{market}"
