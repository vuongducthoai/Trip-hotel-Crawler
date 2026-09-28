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
import zipfile
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
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
import destinations
import raw_store
from crawl_fast import raw_city_id, raw_city_info, raw_complete
from crawl_jobs import JobRunner
import kho_du_lieu
import kiem_tra
import danh_sach_id

HOST, PORT = "127.0.0.1", 8765
WEB_DIR = ROOT / "web"
CSV_DIR = config.OUTPUT_DIR / "csv"
DOWNLOAD_STATE_PATH = config.OUTPUT_DIR / "trang_thai_tai_csv.json"
DOWNLOAD_LOCK = threading.Lock()
RUNNER = JobRunner()
LOG_DIR = config.OUTPUT_DIR / "logs"


class _Tee:
    """Ghi stdout/stderr của server ra cả console lẫn file logs/server.log (xoay khi > 5 MB)."""

    def __init__(self, stream, path: Path, limit: int = 5 * 1024 * 1024):
        self.stream = stream
        self.path = path
        self.limit = limit
        self.lock = threading.Lock()

    def write(self, data: str) -> int:
        try:
            self.stream.write(data)
        except Exception:
            pass
        if not data.strip():
            return len(data)
        try:
            with self.lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                if self.path.exists() and self.path.stat().st_size > self.limit:
                    self.path.replace(self.path.with_suffix(".1.log"))
                with self.path.open("a", encoding="utf-8") as handle:
                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    for line in data.rstrip("\n").splitlines():
                        handle.write(f"{stamp} {line}\n")
        except Exception:
            pass
        return len(data)

    def flush(self) -> None:
        try:
            self.stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self.stream, name)


sys.stdout = _Tee(sys.stdout, LOG_DIR / "server.log")
sys.stderr = _Tee(sys.stderr, LOG_DIR / "server.log")
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

    known = destinations.find_by_city_id(city_id) or next((city for city in config.VN_CITIES if city.get("id") == city_id), None)
    city_name = next((query.get(key) for key in ("cityname", "searchword", "destname") if query.get(key)), None)
    if city_name:
        city_name = city_name.split(",", 1)[0].strip()
    if not city_name and known:
        city_name = known.get("city_name") or known.get("name")
    if not city_name:
        slug = unquote(parsed.path.rstrip("/").split("/")[-1]).replace("-", " ").strip()
        city_name = slug if slug and slug.lower() not in {"list", "hotels"} else f"Thành phố {city_id}"

    country_raw = next((query.get(key) for key in ("countryid", "country") if query.get(key)), None)
    country_id = int(country_raw) if country_raw and str(country_raw).isdigit() else int((known or {}).get("country_id") or 111)
    province_raw = query.get("provinceid")
    province_id = int(province_raw) if province_raw and str(province_raw).isdigit() else int((known or {}).get("province_id") or 0)
    country_name = next((query.get(key) for key in ("countryname",) if query.get(key)), None)
    if not country_name and query.get("destname") and "," in query["destname"]:
        country_name = query["destname"].split(",", 1)[1].strip()
    country_name = country_name or COUNTRY_NAMES.get(country_id) or (known and known.get("country_name")) or destinations.find_country_name(country_id)
    return {"city_id": city_id, "province_id": province_id, "country_id": country_id,
            "city_name": city_name, "country_name": country_name}


BACKUP_DIR = config.DATA_ROOT / "backups"
BACKUP_LOCK = threading.Lock()


def _backup_members():
    """Các file trong output/ cần sao lưu (bỏ file tạm, log, thư mục _to_delete)."""
    root = config.OUTPUT_DIR
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if parts and parts[0] in {"_to_delete", "backups", "recon", "html"}:
            continue
        if path.suffix == ".tmp" or ".write-test" in path.name:
            continue
        yield path, rel


def create_backup() -> dict:
    import zipfile
    if not BACKUP_LOCK.acquire(blocking=False):
        raise RuntimeError("Đang có một lượt sao lưu chạy.")
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        name = f"trip-hotel-data_{datetime.now():%Y%m%d_%H%M%S}.zip"
        target = BACKUP_DIR / name
        temporary = target.with_suffix(".zip.tmp")
        count = 0
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path, rel in _backup_members():
                # raw đã nén .gz → lưu thẳng cho nhanh, không nén lại.
                ctype = zipfile.ZIP_STORED if path.suffix == ".gz" else zipfile.ZIP_DEFLATED
                zf.write(path, str(Path("output") / rel), compress_type=ctype)
                count += 1
        temporary.replace(target)
        return {"ok": True, "ten": name, "duong_dan": str(target),
                "kich_thuoc": target.stat().st_size, "so_file": count}
    finally:
        BACKUP_LOCK.release()


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    return [{"ten": p.name, "kich_thuoc": p.stat().st_size,
             "cap_nhat": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(BACKUP_DIR.glob("trip-hotel-data_*.zip"),
                            key=lambda p: p.stat().st_mtime, reverse=True)]


def restore_backup(name: str, replace: bool = False) -> dict:
    import zipfile
    status = RUNNER.status().get("current")
    if status and status.get("running"):
        raise RuntimeError("Đang có tác vụ chạy; hãy đợi xong hoặc bấm Dừng rồi khôi phục.")
    path = (BACKUP_DIR / name).resolve()
    if path.parent != BACKUP_DIR.resolve() or not path.is_file() or path.suffix != ".zip":
        raise FileNotFoundError("Không tìm thấy file sao lưu.")
    restored = skipped = 0
    with zipfile.ZipFile(path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            rel = Path(member.filename)
            if not rel.parts or rel.parts[0] != "output" or ".." in rel.parts:
                continue
            dest = (config.OUTPUT_DIR / Path(*rel.parts[1:])).resolve()
            if config.OUTPUT_DIR.resolve() not in dest.parents:
                continue
            if dest.exists() and not replace:
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, dest.open("wb") as out:
                out.write(src.read())
            restored += 1
    kho_du_lieu._CACHE.clear()
    kho_du_lieu._LIST_MEMO.update(at=0.0, value=None)
    return {"ok": True, "phuc_hoi": restored, "bo_qua": skipped}


def app_version() -> str:
    if os.getenv("TRIP_APP_VERSION"):
        return os.getenv("TRIP_APP_VERSION", "")
    try:
        return json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):
        return ""


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
    return {"total_raw": total, "theo_ngon_ngu": counts, "thu_muc_du_lieu": str(config.DATA_ROOT), "phien_ban": app_version(),
            "muc_tieu": (status or {}).get("total", 0), "dang_chay": bool(status and status["running"])}


class Handler(BaseHTTPRequestHandler):
    server_version = "TripHotelData/1.1"

    def log_message(self, format, *args):
        # Bỏ qua các request hỏi trạng thái định kỳ cho log đỡ rác.
        message = format % args
        if "/api/crawl/jobs" in message or "/api/tien-do" in message:
            return
        print(f"HTTP · {message}")

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
            if parsed.path == "/api/destinations":
                return self.send_json(destinations.get_catalog())
            if parsed.path == "/api/crawl/jobs":
                return self.send_json(RUNNER.status())
            if parsed.path == "/api/tien-do":
                return self.send_json(raw_progress())
            if parsed.path == "/api/crawl/cities":
                return self.send_json({"cities": all_city_stats()})
            if parsed.path == "/api/du-lieu/sao-luu":
                return self.send_json({"files": list_backups(), "thu_muc": str(BACKUP_DIR)})
            if parsed.path == "/api/kho/chat-luong":
                q = parse_qs(parsed.query)
                city_ids = {int(x) for x in q.get("city_ids", [""])[0].split(",") if x.strip().lstrip("-").isdigit()} or None
                chi_moi = (q.get("chi_moi", ["0"])[0] or "0") not in ("0", "", "false")
                return self.send_json(kho_du_lieu.chat_luong(kho_du_lieu.danh_sach(), city_ids, chi_moi=chi_moi))
            if parsed.path == "/api/kho/danh-sach":
                items = kho_du_lieu.danh_sach()
                return self.send_json({"khach_san": items, "thong_ke": kho_du_lieu.thong_ke(items)})
            if parsed.path.startswith("/api/kho/khach-san/"):
                hotel_id = unquote(parsed.path.removeprefix("/api/kho/khach-san/")).strip("/")
                if not hotel_id.isdigit():
                    raise ValueError("Mã khách sạn không hợp lệ.")
                lang = (parse_qs(parsed.query).get("lang") or ["vi"])[0]
                try:
                    return self.send_json(kho_du_lieu.chi_tiet(hotel_id, lang))
                except FileNotFoundError as exc:
                    return self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
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
        except (ValueError, FileNotFoundError) as exc:
            print(f"TỪ CHỐI GET {parsed.path}: {exc}", file=sys.stderr)
            return self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            import traceback
            print(f"LỖI GET {parsed.path}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
            return self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST(self):
        if self.path.startswith("/api/danh-sach/tai-file"):
            return self.upload_id_file()
        try:
            body = self.read_json()
            if self.path == "/api/destinations/preview":
                city_id = int(body.get("city_id") or 0)
                item = destinations.find_by_city_id(city_id)
                if not item:
                    raise ValueError("Không tìm thấy thành phố trong danh mục.")
                locale = str(body.get("locale") or "vi-VN")
                currency = str(body.get("currency") or "VND")
                tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
                import crawl_api
                url = crawl_api.build_list_url(
                    {"id": item["city_id"], "name": item["city_name"], "province_id": item["province_id"],
                     "country_id": item["country_id"], "country_name": item["country_name"]},
                    tomorrow, day_after, locale, currency
                )
                return self.send_json({
                    "place": item,
                    "url": url,
                    "languages": city_storage_stats(city_id),
                })
            if self.path == "/api/kiem-tra":
                languages = [l for l in (body.get("ngon_ngu") or ["vi"]) if l in {"vi", "en"}] or ["vi"]
                city = None
                if body.get("city_id"):
                    item = destinations.find_by_city_id(int(body["city_id"]))
                    if item:
                        city = {"id": item["city_id"], "name": item["city_name"], "name_en": item["city_name"],
                                "province_id": item["province_id"], "country_id": item["country_id"],
                                "country_name": item["country_name"], "country_name_en": item["country_name"]}
                return self.send_json(kiem_tra.kiem_tra(languages, city, probe=bool(body.get("probe", True))))
            if self.path == "/api/crawl/queue/remove":
                return self.send_json(RUNNER.remove_from_queue(int(body.get("id", 0))))
            if self.path == "/api/crawl/queue/clear":
                return self.send_json(RUNNER.clear_queue())
            if self.path == "/api/crawl/start":
                amount = int(body.get("so_luong", 0))
                if not 1 <= amount <= 100_000:
                    raise ValueError("Số lượng phải từ 1 đến 100.000.")
                languages = body.get("ngon_ngu") or []
                if not languages or any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Hãy chọn ít nhất một ngôn ngữ hợp lệ.")
                if body.get("city_ids"):
                    # Hàng đợi nhiều thành phố: thành phố nào đã có raw thì cào tiếp (bỏ qua KS đủ).
                    params_list = []
                    for raw_id in body["city_ids"]:
                        item = destinations.find_by_city_id(int(raw_id))
                        if not item:
                            raise ValueError(f"Không tìm thấy thành phố {raw_id} trong danh mục.")
                        stats = city_storage_stats(item["city_id"])
                        has_data = any(v["total"] for v in stats.values())
                        params_list.append({
                            "city_id": item["city_id"], "province_id": item["province_id"],
                            "country_id": item["country_id"], "city_name": item["city_name"],
                            "country_name": item["country_name"], "limit": amount,
                            "continue_mode": has_data, "languages": list(dict.fromkeys(languages)),
                        })
                    return self.send_json(RUNNER.enqueue_crawls(params_list), HTTPStatus.ACCEPTED)
                if body.get("city_id"):
                    item = destinations.find_by_city_id(int(body["city_id"]))
                    if not item:
                        raise ValueError("Không tìm thấy thành phố trong danh mục.")
                    place = {
                        "city_id": item["city_id"],
                        "province_id": item["province_id"],
                        "country_id": item["country_id"],
                        "city_name": item["city_name"],
                        "country_name": item["country_name"],
                    }
                else:
                    place = parse_trip_url(str(body.get("url") or ""))
                return self.send_json(RUNNER.start_crawl({**place, "limit": amount,
                                                          "continue_mode": bool(body.get("tiep_tuc")),
                                                          "languages": list(dict.fromkeys(languages))}),
                                      HTTPStatus.ACCEPTED)
            if self.path == "/api/crawl/thong-ke":
                if body.get("city_id"):
                    item = destinations.find_by_city_id(int(body["city_id"]))
                    if not item:
                        raise ValueError("Không tìm thấy thành phố trong danh mục.")
                    place = {
                        "city_id": item["city_id"],
                        "province_id": item["province_id"],
                        "country_id": item["country_id"],
                        "city_name": item["city_name"],
                        "country_name": item["country_name"],
                    }
                else:
                    place = parse_trip_url(str(body.get("url") or ""))
                return self.send_json({**place, "languages": city_storage_stats(place["city_id"])})
            if self.path == "/api/crawl/stop":
                return self.send_json(RUNNER.stop(), HTTPStatus.ACCEPTED)
            if self.path == "/api/crawl/history/clear":
                return self.send_json(RUNNER.clear_history())
            if self.path == "/api/danh-sach/phan-tich":
                result = danh_sach_id.phan_tich(str(body.get("text") or ""))
                # Đối chiếu với kho: ID nào đã có raw (theo ngôn ngữ), đã đủ chưa
                trong_kho = {it["trip_hotel_id"]: it for it in kho_du_lieu.danh_sach()}
                da_co = {}
                for hid in result["ids"]:
                    it = trong_kho.get(hid)
                    if it:
                        da_co[hid] = {lang: bool(ban.get("hoan_chinh")) for lang, ban in it["ngon_ngu"].items()}
                        da_co[hid]["ten"] = it["ten"]
                        da_co[hid]["city_name"] = it["city_name"]
                result["da_co"] = da_co
                return self.send_json(result)
            if self.path == "/api/crawl/start-ids":
                ids = [str(x).strip() for x in (body.get("ids") or []) if str(x).strip().isdigit()]
                if not ids:
                    raise ValueError("Danh sách không có ID hợp lệ.")
                if len(ids) > danh_sach_id.MAX_ITEMS:
                    raise ValueError(f"Mỗi lần tối đa {danh_sach_id.MAX_ITEMS} khách sạn.")
                languages = body.get("ngon_ngu") or ["vi"]
                if any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Ngôn ngữ không hợp lệ.")
                return self.send_json(RUNNER.start_cao_bu(list(dict.fromkeys(ids)), list(dict.fromkeys(languages)),
                                                          bo_qua_da_co=not bool(body.get("cao_lai")),
                                                          nguon="danh_sach"),
                                      HTTPStatus.ACCEPTED)
            if self.path == "/api/kho/cao-bu":
                ids = [str(x).strip() for x in (body.get("ids") or []) if str(x).strip().isdigit()]
                if not ids:
                    raise ValueError("Hãy chọn ít nhất một khách sạn để cào bù.")
                if len(ids) > 5000:
                    raise ValueError("Mỗi lần cào bù tối đa 5.000 khách sạn.")
                languages = body.get("ngon_ngu") or ["vi"]
                if any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Ngôn ngữ không hợp lệ.")
                return self.send_json(RUNNER.start_cao_bu(list(dict.fromkeys(ids)),
                                                          list(dict.fromkeys(languages))),
                                      HTTPStatus.ACCEPTED)
            if self.path == "/api/cookie/refresh":
                languages = body.get("ngon_ngu") or ["vi"]
                if any(lang not in {"vi", "en"} for lang in languages):
                    raise ValueError("Ngôn ngữ không hợp lệ.")
                return self.send_json(RUNNER.start_cookie(list(dict.fromkeys(languages))), HTTPStatus.ACCEPTED)
            if self.path == "/api/csv/xuat":
                return self.export_csv(body)
            if self.path == "/api/du-lieu/sao-luu":
                return self.send_json(create_backup())
            if self.path == "/api/du-lieu/khoi-phuc":
                return self.send_json(restore_backup(str(body.get("ten") or ""), bool(body.get("ghi_de"))))
            if self.path == "/api/du-lieu/mo-thu-muc-sao-luu":
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                open_with_system(BACKUP_DIR)
                return self.send_json({"ok": True})
            if self.path == "/api/du-lieu/mo-thu-muc-log":
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                open_with_system(LOG_DIR)
                return self.send_json({"ok": True, "duong_dan": str(LOG_DIR)})
            if self.path == "/api/du-lieu/mo-thu-muc":
                config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                open_with_system(config.OUTPUT_DIR)
                return self.send_json({"ok": True, "duong_dan": str(config.OUTPUT_DIR)})
            if self.path == "/api/csv/xoa":
                names = body.get("ten") if isinstance(body.get("ten"), list) else [body.get("ten")]
                if body.get("tat_ca"):
                    names = [p.name for p in CSV_DIR.glob("*.csv")]
                deleted = 0
                for name in [n for n in names if n]:
                    path = csv_path(str(name))
                    path.unlink()
                    deleted += 1
                with DOWNLOAD_LOCK:
                    state = download_state()
                    for name in names:
                        state.pop(str(name), None)
                    DOWNLOAD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    DOWNLOAD_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Đã xoá {deleted} file CSV: {', '.join(str(n) for n in names)}")
                return self.send_json({"ok": True, "da_xoa": deleted})
            if self.path == "/api/csv/danh-dau-da-xuat":
                items = kho_du_lieu.danh_sach()
                kho_du_lieu.danh_dau_da_xuat([it["trip_hotel_id"] for it in items])
                print(f"Đã đánh dấu {len(items)} khách sạn là đã xuất CSV (không tạo file).")
                return self.send_json({"ok": True, "so_khach_san": len(items)})
            if self.path == "/api/csv/dat-lai-da-xuat":
                try:
                    kho_du_lieu.EXPORT_STATE_PATH.unlink()
                except FileNotFoundError:
                    pass
                print("Đã đặt lại dấu 'đã xuất CSV' cho toàn bộ khách sạn.")
                return self.send_json({"ok": True})
            if self.path == "/api/du-lieu/xoa-sao-luu":
                name = str(body.get("ten") or "")
                path = (BACKUP_DIR / name).resolve()
                if path.parent != BACKUP_DIR.resolve() or not path.is_file() or path.suffix != ".zip":
                    raise FileNotFoundError("Không tìm thấy file sao lưu.")
                path.unlink()
                return self.send_json({"ok": True})
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
            print(f"TỪ CHỐI POST {self.path}: {exc}", file=sys.stderr)
            self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except (ValueError, FileNotFoundError) as exc:
            print(f"TỪ CHỐI POST {self.path}: {exc}", file=sys.stderr)
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            import traceback
            print(f"LỖI POST {self.path}: {exc}\n{traceback.format_exc()}", file=sys.stderr)
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def upload_id_file(self):
        """Nhận file .txt/.csv/.tsv/.xlsx (body thô), trả về văn bản đã rút + kết quả phân tích."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("File rỗng.")
            if length > 25 * 1024 * 1024:
                raise ValueError("File quá lớn (tối đa 25 MB).")
            name = unquote((parse_qs(urlparse(self.path).query).get("ten") or ["danh_sach.txt"])[0])
            data = self.rfile.read(length)
            text = danh_sach_id.doc_file(name, data)
            result = danh_sach_id.phan_tich(text)
            result["ten_file"] = name
            result["so_dong"] = len([l for l in text.splitlines() if l.strip()])
            print(f"Đã đọc file danh sách {name}: {result['so_dong']} dòng, {len(result['ids'])} ID")
            return self.send_json(result)
        except (ValueError, zipfile.BadZipFile) as exc:
            return self.send_json({"error": f"Không đọc được file: {exc}"}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            import traceback
            print(f"LỖI tải file danh sách: {exc}\n{traceback.format_exc()}", file=sys.stderr)
            return self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    @staticmethod
    def _slug(text: str) -> str:
        import unicodedata
        plain = unicodedata.normalize("NFD", str(text or "")).encode("ascii", "ignore").decode()
        plain = re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_").lower()
        return plain or "thanh_pho"

    def export_csv(self, body: dict | None = None):
        """Xuất CSV: toàn bộ raw, hoặc chỉ một số thành phố / một danh sách ID.

        body = {"city_ids": [58, 2]}  hoặc  {"ids": ["1971156", …]}  hoặc {} = tất cả.
        """
        import xuat_csv

        body = body or {}
        CSV_DIR.mkdir(parents=True, exist_ok=True)
        ids: list[str] | None = None
        label = "tat_ca"
        chi_moi = bool(body.get("chi_moi"))
        city_ids = [int(x) for x in (body.get("city_ids") or []) if str(x).strip().lstrip("-").isdigit()]
        items_all = kho_du_lieu.danh_sach()
        if body.get("ids"):
            ids = [str(x).strip() for x in body["ids"] if str(x).strip().isdigit()]
            label = f"{len(ids)}_khach_san"
        elif city_ids:
            wanted = set(city_ids)
            items = [it for it in items_all if it["city_id"] in wanted]
            ids = [it["trip_hotel_id"] for it in items]
            names = {it["city_id"]: it["city_name"] for it in items}
            label = "_".join(self._slug(names.get(cid, cid)) for cid in city_ids)[:60]
        if chi_moi:
            # Chỉ khách sạn cào/cào lại sau lần xuất gần nhất (chưa nằm trong CSV nào).
            moi = set(kho_du_lieu.chua_xuat_ids(items_all))
            base = ids if ids is not None else [it["trip_hotel_id"] for it in items_all]
            ids = [hid for hid in base if hid in moi]
            label = f"moi_{label}"
            if not ids:
                raise ValueError("Không có khách sạn mới nào kể từ lần xuất trước trong phạm vi này.")
        if ids is not None and not ids:
            raise ValueError("Không có khách sạn nào trong phạm vi đã chọn.")
        name = f"trip_property_translation_{label}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        target = CSV_DIR / name
        args = Namespace(
            thu_muc_raw=str(config.OUTPUT_DIR / "details" / "raw"),
            ids=ids, ids_file=None, ra=str(target), bom=True,
        )
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = xuat_csv.main(args)
        if code:
            raise RuntimeError(output.getvalue().strip() or "Không xuất được CSV.")
        kho_du_lieu.danh_dau_da_xuat(ids if ids is not None else [it["trip_hotel_id"] for it in items_all])
        return self.send_json({"ok": True, "ten": name, "so_khach_san": len(ids) if ids else len(items_all),
                               "log": output.getvalue()})

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
    elif kind == "caobu":
        import runpy
        runpy.run_module("cao_bu", run_name="__main__")
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
