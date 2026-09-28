"""Nhận danh sách khách sạn do người dùng đưa (ID hoặc URL Trip.com) từ văn bản hoặc file.

- Văn bản: mỗi dòng/ô một mục; nhận số thuần (hotelId) hoặc URL chứa hotelId=…,
  /hotels/detail/<id>, hotels/<id>… Bỏ dòng trống, dòng bắt đầu bằng #.
- File: .txt, .csv, .tsv (mọi ô), .xlsx (đọc bằng zipfile + XML, không cần thư viện).
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

ID_RE = re.compile(r"^\d{4,12}$")
URL_ID_PATTERNS = (
    re.compile(r"[?&]hotel[iI]d=(\d{4,12})"),
    re.compile(r"/hotels?/detail/(\d{4,12})"),
    re.compile(r"/hotels?/[^/?#]*?(\d{4,12})(?:\.html)?(?:[/?#]|$)"),
)
MAX_ITEMS = 5000


def trich_id(raw: str) -> str | None:
    text = str(raw or "").strip().strip('"\'')
    if not text:
        return None
    if ID_RE.match(text):
        return text
    if "trip.com" in text.lower() or "hotelid" in text.lower():
        for pattern in URL_ID_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(1)
    # "ID: 123456" / "123456 - Tên khách sạn" → lấy số đầu tiên đủ dài
    m = re.match(r"^\D{0,10}(\d{4,12})\b", text)
    if m:
        return m.group(1)
    return None


def phan_tich(text: str) -> dict:
    """Văn bản nhiều dòng → {ids (duy nhất, giữ thứ tự), trung, khong_hieu}."""
    ids: list[str] = []
    seen: set[str] = set()
    trung = 0
    khong_hieu: list[str] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # một dòng có thể chứa nhiều mục cách nhau bởi dấu phẩy/chấm phẩy/tab
        parts = [p for p in re.split(r"[,\t;]+", line) if p.strip()] if not line.lower().startswith("http") else [line]
        for part in parts:
            hid = trich_id(part)
            if hid is None:
                khong_hieu.append(part.strip()[:120])
                continue
            if hid in seen:
                trung += 1
                continue
            seen.add(hid)
            ids.append(hid)
            if len(ids) >= MAX_ITEMS:
                break
    return {"ids": ids, "trung": trung, "khong_hieu": khong_hieu[:50], "so_khong_hieu": len(khong_hieu)}


def _xlsx_text(data: bytes) -> str:
    """Rút mọi ô của mọi sheet trong .xlsx thành văn bản, mỗi ô một dòng."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    out: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheets = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        for name in sheets:
            root = ET.fromstring(zf.read(name))
            for c in root.iter(f"{{{ns['m']}}}c"):
                t = c.get("t")
                v = c.find("m:v", ns)
                if t == "s" and v is not None and v.text is not None:
                    idx = int(v.text)
                    out.append(shared[idx] if idx < len(shared) else "")
                elif t == "inlineStr":
                    out.append("".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t")))
                elif v is not None and v.text is not None:
                    text = v.text
                    # số dạng 1.971156E6 → trả về nguyên
                    try:
                        if re.match(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$", text):
                            f = float(text)
                            if f.is_integer():
                                text = str(int(f))
                    except ValueError:
                        pass
                    out.append(text)
    return "\n".join(out)


def doc_file(ten: str, data: bytes) -> str:
    """File tải lên → văn bản để đưa vào phan_tich()."""
    lower = ten.lower()
    if lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        return _xlsx_text(data)
    text = None
    for enc in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    text = text or ""
    if lower.endswith((".csv", ".tsv")):
        cells: list[str] = []
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        for row in csv.reader(io.StringIO(text), dialect):
            cells.extend(cell for cell in row if cell.strip())
        return "\n".join(cells)
    return text
