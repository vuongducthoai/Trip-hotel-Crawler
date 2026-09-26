"""Ghi nhận lỗi bóc tách để một bản ghi xấu không làm hỏng cả lần xuất."""
from __future__ import annotations

from dataclasses import asdict, dataclass

ERROR = "error"
WARNING = "warning"
FIXED = "fixed"


@dataclass
class Issue:
    code: str
    severity: str
    entity: str
    key: object = None
    field: str | None = None
    value: object = None
    detail: str | None = None


class Issues:
    def __init__(self, trip_hotel_id=None, locale=None, raw_path=None):
        self.trip_hotel_id = trip_hotel_id
        self.locale = locale
        self.raw_path = raw_path
        self.items: list[Issue] = []

    def add(self, code, entity, key=None, field=None, value=None, detail=None, severity=WARNING):
        self.items.append(Issue(code, severity, entity, key, field, value, detail))

    def fix(self, code, entity="hotel", **kwargs):
        self.add(code, entity, severity=FIXED, **kwargs)

    def hotel_rejected(self) -> bool:
        return any(item.severity == ERROR and item.entity == "hotel" for item in self.items)

    def as_dicts(self) -> list[dict]:
        return [asdict(item) for item in self.items]
