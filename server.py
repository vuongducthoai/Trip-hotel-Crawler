"""HTTP server thư viện chuẩn cho giao diện Electron."""
from __future__ import annotations

import json
import mimetypes
import csv
import os
import re
import socket
import subprocess
import sys
import io
import threading
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = (Path(sys.executable).resolve().parent.parent
        if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT / "src"))

import config
import raw_store
from crawl_fast import raw_city_id, raw_city_info, raw_complete
from crawl_jobs import JobRunner

HOST, PORT = "127.0.0.1", 8765
WEB_DIR = ROOT / "web"
CSV_DIR = config.OUTPUT_DIR / "csv"
DOWNLOAD_STATE_PATH = config.OUTPUT_DIR / "trang_thai_tai_csv.json"
DOWNLOAD_LOCK = threading.Lock()
RUNNER = JobRunner()
COUNTRY_NAMES = {1: "Trung Quốc", 27: "Đan Mạch", 107: "Ấn Độ", 111: "Việt Nam"}


def csv_path(name: str) -> Path:
    """Trả đường dẫn CSV an toàn, không cho thoát khỏi thư mục kết quả."""
    if Path(name).name != name or not name.lower().endswith(".csv"):
        raise ValueError("Tên file CSV không hợp lệ.")
    path = (CSV_DIR / name).resolve()
    if path.parent != CSV_DIR.resolve() or not path.is_file():
        raise FileNotFoundError("Không tìm thấy file CSV.")
    return path


def open_with_system(path: Path) -> None:
    """Mở file/thư mục bằng ứng dụng mặc định của hệ điều hành."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        raise RuntimeError(
            "Windows không tìm thấy ứng dụng để mở CSV. Hãy cài Excel, LibreOffice "
            "hoặc đặt ứng dụng mặc định cho file .csv."
        ) from exc


def download_state() -> dict:
    try:
        value = json.loads(DOWNLOAD_STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_downloaded(name: str) -> None:
    with DOWNLOAD_LOCK:
        state = download_state()
        state[name] = datetime.now().isoformat(timespec="seconds")
        DOWNLOAD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = DOWNLOAD_STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(DOWNLOAD_STATE_PATH)


def city_storage_stats(city_id: int) -> dict:
    """Thống kê raw của một thành phố, tách theo ngôn ngữ và độ hoàn chỉnh."""
    result = {}
    for key, locale, currency in (("vi", "vi-VN", "VND"), ("en", "en-US", "USD")):
        folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency
        total = complete = 0
        for path in raw_store.iter_raw_files(folder):
            hotel_id = raw_store.hotel_id(path)
            if not hotel_id.isdigit():
                continue
            try:
                dump = raw_store.read(path)
            except (OSError, ValueError):
                continue
            if raw_city_id(dump) != city_id:
                continue
            total += 1
            complete += int(raw_complete(dump))
        result[key] = {"total": total, "complete": complete, "incomplete": total - complete}
    return result


def all_city_stats() -> list[dict]:
    """Tổng hợp thành phố đã cào từ raw và các checkpoint danh sách."""
    cities: dict[int, dict] = {}

    def city(city_id: int) -> dict:
        return cities.setdefault(city_id, {
            "city_id": city_id, "city_name": f"Thành phố {city_id}",
            "province_id": 0, "country_id": 0, "country_name": "",
            "raw_ids": set(), "listed_ids": set(),
            "languages": {
                "vi": {"ids": set(), "complete_ids": set()},
                "en": {"ids": set(), "complete_ids": set()},
            },
            "updated_timestamp": 0.0,
        })

    for key, locale, currency in (("vi", "vi-VN", "VND"), ("en", "en-US", "USD")):
        folder = config.OUTPUT_DIR / "details" / "raw" / locale / currency
        for path in raw_store.iter_raw_files(folder):
            hotel_id = raw_store.hotel_id(path)
            if not hotel_id.isdigit():
                continue
            try:
                dump = raw_store.read(path)
            except (OSError, ValueError):
                continue
            info = raw_city_info(dump)
            if not info:
                continue
            item = city(info["city_id"])
            # Ưu tiên tên tiếng Việt; nếu chưa có thì dùng tên từ raw hiện tại.
            if key == "vi" or item["city_name"].startswith("Thành phố "):
                item.update({field: info[field] for field in (
                    "city_name", "province_id", "country_id", "country_name")})
            item["raw_ids"].add(hotel_id)
            item["languages"][key]["ids"].add(hotel_id)
            if raw_complete(dump):
                item["languages"][key]["complete_ids"].add(hotel_id)
            item["updated_timestamp"] = max(item["updated_timestamp"], path.stat().st_mtime)

    for path in config.DATA_DIR.glob("api_hotels_*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            city_id = int(payload.get("city_id"))
        except (OSError, ValueError, TypeError):
            continue
        item = city(city_id)
        if item["city_name"].startswith("Thành phố ") and payload.get("city_name"):
            item["city_name"] = payload["city_name"]
        item["listed_ids"].update(
            str(hotel.get("trip_hotel_id")) for hotel in payload.get("hotels") or []
            if hotel.get("trip_hotel_id")
        )
        item["updated_timestamp"] = max(item["updated_timestamp"], path.stat().st_mtime)

    result = []
    for item in cities.values():
        languages = {}
        for key, values in item["languages"].items():
            languages[key] = {
                "total": len(values["ids"]),
                "complete": len(values["complete_ids"]),
                "incomplete": len(values["ids"] - values["complete_ids"]),
            }
        result.append({
            "city_id": item["city_id"], "city_name": item["city_name"],
            "province_id": item["province_id"], "country_id": item["country_id"],
            "country_name": item["country_name"],
            "total_hotels": len(item["raw_ids"]),
            "listed_hotels": len(item["listed_ids"]),
            "languages": languages,
            "updated_at": datetime.fromtimestamp(item["updated_timestamp"]).isoformat(timespec="seconds")
            if item["updated_timestamp"] else None,
        })
    return sorted(result, key=lambda item: item["updated_at"] or "", reverse=True)


def parse_trip_url(value: str) -> dict:
    """Bóc mã địa điểm và tên thành phố từ URL danh sách Trip.com."""
    try:
        parsed = urlparse(value.strip())
    except ValueError as exc:
        raise ValueError("URL Trip.com không hợp lệ.") from exc
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not (hostname == "trip.com" or hostname.endswith(".trip.com")):
        raise ValueError("Hãy dán URL trang danh sách thuộc trip.com.")
    query = {key.lower(): values[-1] for key, values in parse_qs(parsed.query).items() if values}

    city_raw = next((query.get(key) for key in ("cityid", "city", "optionid") if query.get(key)), None)
    if not city_raw:
        match = re.search(r"(?:city|hotels?)[-_/](\d+)", parsed.path, re.I)
        city_raw = match.group(1) if match else None
    if not city_raw or not str(city_raw).isdigit():
        raise ValueError("Không tìm thấy cityId trong URL. Hãy mở đúng trang kết quả danh sách rồi sao chép URL.")
    city_id = int(city_raw)

    known = next((city for city in config.VN_CITIES if city["id"] == city_id), None)
    city_name = next((query.get(key) for key in ("cityname", "searchword", "destname") if query.get(key)), None)
    if city_name:
        city_name = city_name.split(",", 1)[0].strip()
    if not city_name and known:
        city_name = known["name"]
    if not city_name:
        slug = unquote(parsed.path.rstrip("/").split("/")[-1]).replace("-", " ").strip()
        city_name = slug if slug and slug.lower() not in {"list", "hotels"} else f"Thành phố {city_id}"

    country_raw = next((query.get(key) for key in ("countryid", "country") if query.get(key)), None)
    country_id = int(country_raw) if country_raw and str(country_raw).isdigit() else int((known or {}).get("country_id") or 111)
    province_raw = query.get("provinceid")
    province_id = int(province_raw) if province_raw and str(province_raw).isdigit() else 0
    country_name = next((query.get(key) for key in ("countryname",) if query.get(key)), None)
    if not country_name and query.get("destname") and "," in query["destname"]:
        country_name = query["destname"].split(",", 1)[1].strip()
    country_name = country_name or COUNTRY_NAMES.get(country_id, f"Quốc gia {country_id}")
    return {"city_id": city_id, "province_id": province_id, "country_id": country_id,
            "city_name": city_name, "country_name": country_name}


def raw_progress() -> dict:
    counts: dict[str, int] = {}
    total = 0
    root = config.OUTPUT_DIR / "details" / "raw"
    for locale, currency in (("vi-VN", "VND"), ("en-US", "USD")):
        folder = root / locale / currency
        ids = set()
        if folder.exists():
            for path in folder.glob("*.json*"):
                if ".failed." not in path.name:
                    ids.add(path.name.split(".", 1)[0])
        counts[locale] = len(ids)
        total += len(ids)
    status = RUNNER.status().get("current")
    return {"total_raw": total, "theo_ngon_ngu": counts,
            "muc_tieu": (status or {}).get("total", 0), "dang_chay": bool(status and status["running"])}


class Handler(BaseHTTPRequestHandler):
    server_version = "ToolCrawlerTrip/1.0"

    def log_message(self, format, *args):
        print(f"HTTP · {format % args}")

    def send_json(self, value, status=HTTPStatus.OK):
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("Yêu cầu quá lớn.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Nội dung JSON không hợp lệ.") from exc

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/crawl/jobs":
                return self.send_json(RUNNER.status())
            if parsed.path == "/api/tien-do":
                return self.send_json(raw_progress())
            if parsed.path == "/api/crawl/cities":
                return self.send_json({"cities": all_city_stats()})
            if parsed.path == "/api/csv/danh-sach":
                CSV_DIR.mkdir(parents=True, exist_ok=True)
                downloaded = download_state()
                files = [{"ten": path.name, "kich_thuoc": path.stat().st_size,
                          "cap_nhat": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                          "da_tai": path.name in downloaded, "tai_luc": downloaded.get(path.name)}
                         for path in sorted(CSV_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)]
                return self.send_json({"files": files})
            if parsed.path.startswith("/api/csv/xem/"):
                return self.preview_csv(unquote(parsed.path.removeprefix("/api/csv/xem/")))
            if parsed.path.startswith("/api/csv/tai/"):
                return self.download_csv(unquote(parsed.path.removeprefix("/api/csv/tai/")))
            return self.static_file(parsed.path)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self):
        try:
            body = self.read_json()
            if self.path == "/api/crawl/start":
                amount = int(body.get("so_luong", 0))
                if not 1 <= amount <= 100_000:
                    raise ValueError("Số lượng phải từ 1 đến 100.000.")
                languages = body.get("ngon_ngu") or []
                if not languages or any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Hãy chọn ít nhất một ngôn ngữ hợp lệ.")
                place = parse_trip_url(str(body.get("url") or ""))
                return self.send_json(RUNNER.start_crawl({**place, "limit": amount,
                                                          "continue_mode": bool(body.get("tiep_tuc")),
                                                          "languages": list(dict.fromkeys(languages))}),
                                      HTTPStatus.ACCEPTED)
            if self.path == "/api/crawl/thong-ke":
                place = parse_trip_url(str(body.get("url") or ""))
                return self.send_json({**place, "languages": city_storage_stats(place["city_id"])})
            if self.path == "/api/crawl/stop":
                return self.send_json(RUNNER.stop(), HTTPStatus.ACCEPTED)
            if self.path == "/api/crawl/history/clear":
                return self.send_json(RUNNER.clear_history())
            if self.path == "/api/cookie/refresh":
                languages = body.get("ngon_ngu") or ["vi"]
                if any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Ngôn ngữ không hợp lệ.")
                return self.send_json(RUNNER.start_cookie(list(dict.fromkeys(languages))), HTTPStatus.ACCEPTED)
            if self.path == "/api/csv/xuat":
                return self.export_csv()
            if self.path == "/api/csv/mo-thu-muc":
                CSV_DIR.mkdir(parents=True, exist_ok=True)
                open_with_system(CSV_DIR)
                return self.send_json({"ok": True})
            if self.path.startswith("/api/csv/mo/"):
                name = unquote(self.path.removeprefix("/api/csv/mo/"))
                open_with_system(csv_path(name))
                return self.send_json({"ok": True, "ten": name})
            self.send_json({"error": "Không tìm thấy API."}, HTTPStatus.NOT_FOUND)
        except RuntimeError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def export_csv(self):
        import xuat_csv

        CSV_DIR.mkdir(parents=True, exist_ok=True)
        name = f"trip_property_translation_{datetime.now():%Y%m%d_%H%M%S}.csv"
        target = CSV_DIR / name
        args = Namespace(
            thu_muc_raw=str(config.OUTPUT_DIR / "details" / "raw"),
            ids=None, ids_file=None, ra=str(target), bom=True,
        )
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = xuat_csv.main(args)
        if code:
            raise RuntimeError(output.getvalue().strip() or "Không xuất được CSV.")
        return self.send_json({"ok": True, "ten": name, "log": output.getvalue()})

    def download_csv(self, name: str):
        path = csv_path(name)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        mark_downloaded(name)

    def preview_csv(self, name: str):
        """Đọc tối đa 50 dòng để xem nhanh, không nạp cả file lớn vào trình duyệt."""
        path = csv_path(name)
        rows: list[list[str]] = []
        total = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            columns = next(reader, [])
            for row in reader:
                total += 1
                if len(rows) < 50:
                    rows.append([cell[:1000] for cell in row])
        return self.send_json({"ten": name, "columns": columns, "rows": rows,
                               "tong_dong": total, "gioi_han": 50})


    def static_file(self, request_path: str):
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        path = (WEB_DIR / relative).resolve()
        if WEB_DIR.resolve() not in path.parents or not path.is_file():
            return self.send_json({"error": "Không tìm thấy."}, HTTPStatus.NOT_FOUND)
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Không cho hai phiên app cùng chia sẻ cổng 8765 trên Windows."""

    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def run_worker() -> bool:
    """Điểm vào phụ cho backend đã đóng gói bằng PyInstaller."""
    if len(sys.argv) < 3 or sys.argv[1] != "--worker":
        return False
    kind = sys.argv[2]
    sys.argv = [sys.argv[0], *sys.argv[3:]]
    if kind == "crawl":
        import runpy
        runpy.run_module("crawl_pipeline", run_name="__main__")
    elif kind == "cookie":
        import runpy
        runpy.run_module("cookie_refresh", run_name="__main__")
    else:
        raise SystemExit(f"Worker không hợp lệ: {kind}")
    return True


if __name__ == "__main__" and not run_worker():
    server = ExclusiveThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Server sẵn sàng tại http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
