"""Trích đúng mã và thông tin định danh cần để crawl trang chi tiết."""
from __future__ import annotations

import json
import re


def parse_hotel(entry: dict, city_name: str | None = None) -> dict | None:
    """1 phần tử trong data.hotelList → dict khớp cột bảng `hotels`."""
    info = entry.get("hotelInfo") or {}
    summary = info.get("summary") or {}
    hotel_id = summary.get("hotelId")
    if not hotel_id:
        return None

    name_info = info.get("nameInfo") or {}
    position = info.get("positionInfo") or {}
    address = position.get("address") or position.get("positionDesc")

    return {
        "trip_hotel_id": str(hotel_id),
        "name": name_info.get("name"),
        "name_en": name_info.get("enName"),
        "url": f"https://vn.trip.com/hotels/detail/?hotelId={hotel_id}",
        "address": address,
        "city_name": city_name or position.get("cityName"),
    }


def parse_response(payload: dict, city_name: str | None = None) -> list[dict]:
    """Toàn bộ response JSON → list các dict khách sạn (bỏ qua entry lỗi)."""
    hotel_list = ((payload.get("data") or {}).get("hotelList")) or []
    out = []
    for entry in hotel_list:
        row = parse_hotel(entry, city_name)
        if row:
            out.append(row)
    return out


def is_last_page(payload: dict) -> bool:
    addi = ((payload.get("data") or {}).get("hotelListAddtionInfo")) or {}
    return bool(addi.get("isLastPage"))


def total_count(payload: dict) -> int | None:
    addi = ((payload.get("data") or {}).get("hotelListAddtionInfo")) or {}
    return addi.get("hotelTotalCount")


# ------------------------------------------------------------------ SSR HTML
# Trang 1 KHÔNG đến từ API — Trip.com nhúng sẵn vào HTML qua Next.js
# (self.__next_f.push). Phải bóc từ đó, nếu không sẽ tưởng là crawl rỗng.

_NEXT_F = re.compile(r'self\.__next_f\.push\(\[1\s*,\s*("(?:[^"\\]|\\.)*")')


def _next_f_text(html: str) -> str:
    """Ghép lại toàn bộ flight data của Next.js, đã giải mã escape."""
    parts = []
    for m in _NEXT_F.finditer(html):
        try:
            parts.append(json.loads(m.group(1)))
        except Exception:
            continue
    return "".join(parts)


def _balanced_object(s: str, start: int) -> str | None:
    """Cắt đúng một object JSON cân ngoặc từ vị trí '{' đầu tiên."""
    depth = 0
    in_str = esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def extract_from_html(html: str, city_name: str | None = None) -> tuple[list[dict], dict]:
    """HTML trang danh sách → (danh sách khách sạn, meta).

    meta: {'total': tổng KS của thành phố, 'is_last_page': bool}
    """
    text = _next_f_text(html)
    i = text.find('"initListData"')
    if i < 0:
        return [], {}
    j = text.find("{", i)
    if j < 0:
        return [], {}
    blob = _balanced_object(text, j)
    if not blob:
        return [], {}
    try:
        data = json.loads(blob)
    except Exception:
        return [], {}

    rows = parse_response({"data": data}, city_name=city_name)
    addi = data.get("hotelListAddtionInfo") or {}
    return rows, {
        "total": addi.get("hotelTotalCount"),
        "is_last_page": bool(addi.get("isLastPage")),
    }


def extract_next_object(html: str, key: str) -> dict | None:
    """Lấy một object có tên từ Next.js flight data.

    Một số phiên Trip.com không SSR danh sách nữa (``initListData`` rỗng)
    nhưng vẫn nhúng toàn bộ body gọi API trong ``initListRequest``.
    """
    text = _next_f_text(html)
    marker = json.dumps(key) + ":"
    i = text.find(marker)
    if i < 0:
        return None
    start = text.find("{", i + len(marker))
    if start < 0:
        return None
    blob = _balanced_object(text, start)
    if not blob:
        return None
    try:
        value = json.loads(blob)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


# --------------------------------------------------------- dò nguồn chưa biết
def find_hotel_lists(obj, path: str = "") -> list[tuple[str, list]]:
    """Quét sâu một JSON bất kỳ, tìm mảng chứa khách sạn.

    Dùng để phát hiện endpoint phân trang mà mình chưa biết tên.
    """
    found: list[tuple[str, list]] = []

    def looks_like_hotel(item) -> bool:
        if not isinstance(item, dict):
            return False
        if "hotelInfo" in item:
            return True
        if "hotelId" in item:          # dạng phẳng, không lồng trong summary
            return True
        summary = item.get("summary") or item.get("hotelBaseInfo")
        return isinstance(summary, dict) and "hotelId" in summary

    def walk(o, p: str, depth: int) -> None:
        if depth > 8:
            return
        if isinstance(o, list):
            if o and looks_like_hotel(o[0]):
                found.append((p, o))
                return
            for k, v in enumerate(o[:5]):
                walk(v, f"{p}[{k}]", depth + 1)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{p}.{k}" if p else k, depth + 1)

    walk(obj, path, 0)
    return found


def dedupe(rows: list[dict]) -> list[dict]:
    """Mỗi mã khách sạn chỉ xuất hiện một lần, giữ bản gặp đầu tiên."""
    best: dict[str, dict] = {}
    for r in rows:
        key = r["trip_hotel_id"]
        best.setdefault(key, r)
    return list(best.values())
