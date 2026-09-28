"""Bóc raw JSON thành bundle chỉ gồm mô tả, chính sách và địa điểm lân cận."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from hotel_description import clean_description, description_text
from . import models as M
from .rules import ERROR, Issues

NEARBY_API = "ctGetNearbyPlaceInfo"
NHAN_LOAI = re.compile(r"^\s*\{0\}(.+?)\{/0\}\s*[:：]")


@dataclass
class Bundle:
    trip_hotel_id: str
    locale: str
    raw_locale: str
    currency: str
    crawled_at: datetime | None
    raw_path: str | None
    country: M.Country | None = None
    hotel: M.Hotel | None = None
    hotel_i18n: M.HotelI18n | None = None
    policy_sections: list[M.PolicySection] = field(default_factory=list)
    nearby: list[M.NearbyPlace] = field(default_factory=list)

    def sections(self) -> dict[str, bool]:
        return {
            "description": bool(self.hotel_i18n and self.hotel_i18n.description),
            "policies": bool(self.policy_sections),
            "nearby": bool(self.nearby),
        }


def short_locale(locale: str) -> str:
    return locale.split("-")[0].lower()


def api(dump: dict, name: str) -> Any:
    for packet in dump.get("responses") or []:
        if name in str(packet.get("url") or ""):
            return packet.get("response")
    return None


def toa_do(value: Any) -> float | None:
    """Trip.com trả lat/lng dạng chuỗi; giá trị trống/0 coi như không có."""
    try:
        so = float(value)
    except (TypeError, ValueError):
        return None
    return so if so and so == so else None


def find_detail(dump: dict) -> dict | None:
    value = api(dump, "embedded:hotel-detail-response")
    return value if isinstance(value, dict) else None


def text(value: Any) -> str | None:
    if value is None:
        return None
    value = re.sub(r"\{/?\d+\}", "", str(value))
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    value = " ".join(value.split())
    return value or None


def integer(value: Any) -> int | None:
    found = re.search(r"\d+", str(value or ""))
    return int(found.group()) if found else None


def decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def valid(model, values: dict, issues: Issues, entity: str, key=None):
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        issues.add("record_invalid", entity, key=key, detail=str(exc))
        return None


def policy_lines(content: list) -> list[tuple[str | None, str, bool]]:
    result: list[tuple[str | None, str, bool]] = []

    def add(label, value, in_table=False):
        label, value = text(label), text(value)
        if value:
            result.append((label.rstrip(":").strip() if label else None, value, in_table))

    for item in content or []:
        if not isinstance(item, dict):
            continue
        add(item.get("title"), item.get("description"))
        table = item.get("tab")
        if not isinstance(table, dict):
            continue
        for row in table.get("tableItems") or []:
            cells = [text(cell.get("content")) for cell in row.get("tableDetails") or []
                     if isinstance(cell, dict)]
            cells = [cell for cell in cells if cell]
            if cells:
                add(cells[0] if len(cells) > 1 else None,
                    " · ".join(cells[1:]) if len(cells) > 1 else cells[0], True)
    return result


def room_count(detail: dict, described: dict | None) -> int | None:
    labels = ((detail.get("hotelDescriptionInfo") or {}).get("lables")
              or ((described or {}).get("hotelDescriptionInfo") or {}).get("lables") or [])
    for label in labels:
        candidate = label.get("title") if isinstance(label, dict) else label
        match = re.search(r"(?:số\s*phòng|number\s+of\s+rooms|rooms?)\s*[:：]\s*(\d+)",
                          str(candidate or ""), re.I)
        if match:
            return int(match.group(1))
    return None


def build_bundle(dump: dict, *, raw_locale: str, currency: str,
                 raw_path: str | None = None, file_hotel_id: str | None = None,
                 detail: dict | None = None) -> tuple[Bundle | None, Issues]:
    locale = short_locale(raw_locale)
    target = dump.get("target") or {}
    normalized = dump.get("normalized") or {}
    hotel_id = str(file_hotel_id or target.get("hotel_id") or normalized.get("trip_hotel_id") or "")
    issues = Issues(hotel_id or None, locale, raw_path)
    if not hotel_id.isdigit():
        issues.add("missing_hotel_id", "hotel", severity=ERROR)
        return None, issues
    if normalized.get("success") is False:
        issues.add("crawl_failed", "hotel", value=normalized.get("error"), severity=ERROR)
        return None, issues

    crawled_at = None
    try:
        crawled_at = datetime.fromisoformat(str(normalized.get("crawled_at")))
    except (TypeError, ValueError):
        pass
    bundle = Bundle(hotel_id, locale, raw_locale, currency, crawled_at, raw_path)
    detail = detail or find_detail(dump) or {}
    base = detail.get("hotelBaseInfo") or {}
    position = detail.get("hotelPositionInfo") or {}
    name_info = base.get("nameInfo") or {}

    if base.get("countryId"):
        bundle.country = valid(M.Country, {
            "trip_country_id": base.get("countryId"), "name": text(base.get("countryName"))
        }, issues, "country")
    described = api(dump, "embedded:hotel-description")
    bundle.hotel = valid(M.Hotel, {
        "trip_hotel_id": int(hotel_id), "room_count": room_count(detail, described),
        "latitude": toa_do(position.get("lat")), "longitude": toa_do(position.get("lng")),
    }, issues, "hotel", hotel_id)

    description = description_text(((described or {}).get("hotelDescriptionInfo") or {}))
    if not description:
        description = description_text(detail.get("hotelDescriptionInfo") or {})
    if not description:
        description = clean_description(normalized.get("description"))
    name = text(name_info.get("name") or normalized.get("name") or target.get("name"))
    if not name:
        issues.add("missing_name", "hotel", severity=ERROR)
        return None, issues
    local_name = text(name_info.get("localNameTip"))
    if local_name and ":" in local_name:
        local_name = local_name.split(":", 1)[1].strip() or None
    if local_name == name:
        local_name = None
    bundle.hotel_i18n = valid(M.HotelI18n, {
        "locale": locale,
        "name": name,
        "local_name": local_name,
        "address": text(position.get("address") or normalized.get("address")),
        "description": description,
    }, issues, "hotel_i18n", hotel_id)
    if bundle.hotel_i18n is None:
        return None, issues

    order = 0
    for code, section in (detail.get("hotelPolicyInfo") or {}).items():
        if not isinstance(section, dict) or not section.get("title"):
            continue
        lines = policy_lines(section.get("content") or [])
        if code == "credit" and not lines:
            cash = text(section.get("cashDesc"))
            lines = [(None, cash, False)] if cash else []
        if not lines:
            continue
        row = valid(M.PolicySection, {
            "locale": locale, "section_code": str(code), "sort_order": order,
            "title": text(section.get("title")), "lines": lines,
        }, issues, "policy", code)
        if row:
            bundle.policy_sections.append(row)
            order += 1

    nearby = api(dump, NEARBY_API) or {}
    groups = (nearby.get("data") or nearby).get("placeInfoList") or []
    seen: set[int] = set()
    mode = {"LINEAR_DISTANCE": "straight_line", "WALK": "walk", "WALKING": "walk",
            "DRIVE": "drive", "DRIVING": "drive"}
    order = 0
    for group in groups:
        for place in group.get("places") or []:
            poi = place.get("id")
            if not isinstance(poi, int) or poi in seen:
                continue
            distance = decimal(place.get("distance"))
            label_match = NHAN_LOAI.match(str(place.get("newName") or ""))
            row = valid(M.NearbyPlace, {
                "trip_poi_id": poi,
                "poi_type": place.get("poiType"),
                "latitude": float(place["lat"]) if place.get("lat") not in (None, "") else None,
                "longitude": float(place["lng"]) if place.get("lng") not in (None, "") else None,
                "locale": locale,
                "name": text(place.get("name")),
                "kind": text((place.get("tagNames") or [None])[0]),
                "type_label": text(label_match.group(1)) if label_match else None,
                "group_code": group.get("id") if isinstance(group.get("id"), int) else 0,
                "group_name": text(group.get("name")),
                "distance_km": distance.quantize(Decimal("0.001")) if distance is not None else None,
                "travel_mode": mode.get(str(place.get("arrivalType") or "").upper(), "unknown"),
                "distance_text": text(place.get("distanceDesc")),
                "sort_order": order,
            }, issues, "place", poi)
            if row:
                bundle.nearby.append(row)
                seen.add(poi)
                order += 1
    return (None, issues) if issues.hotel_rejected() else (bundle, issues)
