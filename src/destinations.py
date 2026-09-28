"""Quản lý danh mục 151 quốc gia quốc tế và 1.050 thành phố cào Trip.com (không gồm Việt Nam),
hỗ trợ ưu tiên các điểm đến có gắn nhãn #Vinfast và #GreenSM lên đầu danh sách."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = (Path(sys.executable).resolve().parent.parent
        if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent)

DATA_PATH = ROOT / "data" / "destinations.json"

BY_CITY_ID: dict[int, dict] = {}
BY_COUNTRY: dict[str, list[dict]] = {}
COUNTRY_NAME_BY_ID: dict[int, str] = {}
COUNTRY_TAGS: dict[str, list[str]] = {}
ALL_CITIES: list[dict] = []
COUNTRIES: list[str] = []


def _load():
    global COUNTRIES, ALL_CITIES, BY_CITY_ID, BY_COUNTRY, COUNTRY_NAME_BY_ID, COUNTRY_TAGS
    if not DATA_PATH.exists():
        return
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[destinations] Lỗi đọc {DATA_PATH}: {exc}", file=sys.stderr)
        return

    # Khởi tạo lại cấu trúc
    BY_CITY_ID.clear()
    BY_COUNTRY.clear()
    COUNTRY_NAME_BY_ID.clear()
    COUNTRY_TAGS.clear()
    ALL_CITIES.clear()

    # Thu thập metadata và xử lý các quốc gia hợp lệ (loại trừ Vietnam)
    valid_country_names = [c for c in raw.keys() if c != "Vietnam"]

    # Bóc tách trước tags và danh sách thành phố của từng nước
    country_data: dict[str, dict] = {}
    for country_name in valid_country_names:
        country_info = raw[country_name]
        c_id = int(country_info.get("countryId", 0))
        COUNTRY_NAME_BY_ID[c_id] = country_name

        c_tags = set(country_info.get("tags") or [])
        city_list = []
        for city in country_info.get("cities", []):
            city_tags = list(city.get("tags") or [])
            c_tags.update(city_tags)

            item = {
                "city_id": int(city["cityId"]),
                "city_name": str(city["cityName"]),
                "province_id": int(city.get("provinceId") or 0),
                "province_name": str(city.get("provinceName") or ""),
                "country_id": c_id,
                "country_name": country_name,
                "tags": city_tags,
            }
            cli_item = {
                "id": item["city_id"],
                "name": item["city_name"],
                "province_id": item["province_id"],
                "country_id": c_id,
                "country_name": country_name,
                "tags": city_tags,
            }
            city_list.append(item)
            ALL_CITIES.append(cli_item)
            BY_CITY_ID[item["city_id"]] = item

        # Sắp xếp thành phố: thành phố có tags lên trước (A-Z), tiếp sau là các thành phố không có tag (A-Z)
        tagged_cities = sorted([c for c in city_list if c.get("tags")], key=lambda x: x["city_name"].lower())
        untagged_cities = sorted([c for c in city_list if not c.get("tags")], key=lambda x: x["city_name"].lower())
        sorted_cities = tagged_cities + untagged_cities

        sorted_country_tags = sorted(list(c_tags))
        COUNTRY_TAGS[country_name] = sorted_country_tags
        BY_COUNTRY[country_name] = sorted_cities
        country_data[country_name] = {
            "has_tags": bool(sorted_country_tags),
        }

    # Sắp xếp danh sách quốc gia: quốc gia có tags xếp trước (A-Z), sau đó là các quốc gia không có tag (A-Z)
    tagged_countries = sorted([c for c in valid_country_names if country_data[c]["has_tags"]])
    untagged_countries = sorted([c for c in valid_country_names if not country_data[c]["has_tags"]])
    COUNTRIES = tagged_countries + untagged_countries


_load()


def get_catalog() -> dict:
    return {
        "countries": COUNTRIES,
        "catalog": BY_COUNTRY,
        "country_tags": COUNTRY_TAGS,
    }


def find_by_city_id(city_id: int | str) -> dict | None:
    try:
        return BY_CITY_ID.get(int(city_id))
    except (TypeError, ValueError):
        return None


def find_country_name(country_id: int | str) -> str:
    try:
        cid = int(country_id)
        return COUNTRY_NAME_BY_ID.get(cid, f"Quốc gia {cid}")
    except (TypeError, ValueError):
        return f"Quốc gia {country_id}"


def all_cities() -> list[dict]:
    return ALL_CITIES
