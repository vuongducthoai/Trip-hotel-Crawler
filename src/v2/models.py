"""Model tối thiểu cho ba nhóm dữ liệu được xuất: mô tả, chính sách, lân cận."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Locale = Field(pattern=r"^[a-z]{2}$")


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Country(Row):
    trip_country_id: int = Field(gt=0)
    name: Optional[str] = None


class Hotel(Row):
    trip_hotel_id: int = Field(gt=0)
    room_count: Optional[int] = Field(default=None, ge=1, le=10000)


class HotelI18n(Row):
    locale: str = Locale
    name: str = Field(min_length=1)
    local_name: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None


class PolicySection(Row):
    locale: str = Locale
    section_code: str = Field(min_length=1)
    sort_order: int = Field(ge=0)
    title: str = Field(min_length=1)
    lines: list[tuple[Optional[str], str, bool]] = Field(default_factory=list)

    @field_validator("lines")
    @classmethod
    def lines_have_text(cls, value):
        if any(not text.strip() for _, text, _ in value):
            raise ValueError("Có dòng chính sách rỗng.")
        return value


class NearbyPlace(Row):
    trip_poi_id: int = Field(gt=0)
    poi_type: Optional[int] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    locale: str = Locale
    name: str = Field(min_length=1)
    kind: Optional[str] = None
    type_label: Optional[str] = None
    group_code: int
    group_name: Optional[str] = None
    distance_km: Optional[Decimal] = Field(default=None, ge=0)
    travel_mode: Literal["walk", "drive", "straight_line", "unknown"] = "unknown"
    distance_text: Optional[str] = None
    sort_order: Optional[int] = None
