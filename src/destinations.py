"""Quản lý danh mục 19 quốc gia quốc tế và 81 thành phố crawl Trip.com (không gồm Việt Nam)."""
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
ALL_CITIES: list[dict] = []
COUNTRIES: list[str] = []


def _load():
    global COUNTRIES, ALL_CITIES, BY_CITY_ID, BY_COUNTRY, COUNTRY_NAME_BY_ID
    if not DATA_PATH.exists():
        return
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[destinations] Lỗi đọc {DATA_PATH}: {exc}", file=sys.stderr)
        return

    # Sắp xếp chữ cái các quốc gia, loại trừ Vietnam nếu có
    sorted_countries = sorted(c for c in raw.keys() if c != "Vietnam")
    COUNTRIES = sorted_countries

    for country_name in sorted_countries:
        country_info = raw[country_name]
        c_id = int(country_info.get("countryId", 0))
        COUNTRY_NAME_BY_ID[c_id] = country_name
        city_list = []
        for city in country_info.get("cities", []):
            item = {
                "city_id": int(city["cityId"]),
                "city_name": str(city["cityName"]),
                "province_id": int(city.get("provinceId") or 0),
                "province_name": str(city.get("provinceName") or ""),
                "country_id": c_id,
                "country_name": country_name,
            }
            # Định dạng tương thích CLI crawl_api (id, name, country_id)
            cli_item = {
                "id": item["city_id"],
                "name": item["city_name"],
                "province_id": item["province_id"],
                "country_id": c_id,
                "country_name": country_name,
            }
            city_list.append(item)
            ALL_CITIES.append(cli_item)
            BY_CITY_ID[item["city_id"]] = item
        BY_COUNTRY[country_name] = sorted(city_list, key=lambda x: x["city_name"])


_load()


def get_catalog() -> dict:
    return {"countries": COUNTRIES, "catalog": BY_COUNTRY}


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
