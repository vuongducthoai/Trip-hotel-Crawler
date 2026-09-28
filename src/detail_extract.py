"""Chuẩn hoá ba phần dữ liệu dùng để hiển thị log khi đang crawl."""
from __future__ import annotations

from hotel_description import description_text


def extract_detail(packets: list[dict], hotel_id: str, url: str,
                   currency: str, locale: str) -> dict:
    detail = next((p.get("response") for p in packets
                   if p.get("url") == "embedded:hotel-detail-response"), {}) or {}
    described = next((p.get("response") for p in packets
                      if p.get("url") == "embedded:hotel-description"), {}) or {}
    base = detail.get("hotelBaseInfo") or {}
    position = detail.get("hotelPositionInfo") or {}
    info = described.get("hotelDescriptionInfo") or detail.get("hotelDescriptionInfo") or {}
    nearby = next((p.get("response") for p in packets
                   if "ctGetNearbyPlaceInfo" in str(p.get("url") or "")), {}) or {}
    groups = (nearby.get("data") or nearby).get("placeInfoList") or []
    return {
        "trip_hotel_id": str(hotel_id),
        "url": url,
        "locale": locale,
        "currency": currency,
        "name": (base.get("nameInfo") or {}).get("name"),
        "address": position.get("address"),
        "description": description_text(info),
        "policy_count": sum(1 for value in (detail.get("hotelPolicyInfo") or {}).values()
                            if isinstance(value, dict) and value.get("title") and value.get("content")),
        "nearby_count": sum(len(group.get("places") or []) for group in groups),
    }
