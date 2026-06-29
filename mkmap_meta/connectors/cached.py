from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from mkmap_meta.connectors.base import EventConnector, PriceConnector
from mkmap_meta.models import EventFeature, PriceFeature
from mkmap_meta.storage import dated_path, read_json


class CachedEventConnector(EventConnector):
    def __init__(self, services: list[str] | None = None) -> None:
        self.services = services or ["midterm_forecast", "typhoon", "weather_alert"]

    def fetch_events(self, target_date: date) -> list[EventFeature]:
        events: list[EventFeature] = []
        for service in self.services:
            path = dated_path("features", service, target_date)
            if path.exists():
                events.extend(_load_events(path))
        return events


class CachedPriceConnector(PriceConnector):
    def __init__(self, source_names: list[str] | None = None) -> None:
        self.source_names = source_names or ["kamis_price"]

    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        prices: list[PriceFeature] = []
        for source_name in self.source_names:
            path = dated_path("features", f"{source_name}_{item_code}", target_date)
            if path.exists():
                prices.extend(_load_prices(path))
        return prices


def _load_events(path: Path) -> list[EventFeature]:
    rows = read_json(path)
    if not isinstance(rows, list):
        return []

    events: list[EventFeature] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        events.append(
            EventFeature(
                region_code=row.get("region_code"),
                base_date=date.fromisoformat(row["base_date"]),
                event_type=row["event_type"],
                level=row.get("level"),
                title=row.get("title"),
                description=row.get("description"),
                severity_score=_optional_float(row.get("severity_score")),
                source=row.get("source", "cached"),
                raw=row.get("raw") if isinstance(row.get("raw"), dict) else {},
            )
        )
    return events


def _load_prices(path: Path) -> list[PriceFeature]:
    rows = read_json(path)
    if not isinstance(rows, list):
        return []

    prices: list[PriceFeature] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        prices.append(
            PriceFeature(
                item_code=row["item_code"],
                region_code=row.get("region_code"),
                base_date=date.fromisoformat(row["base_date"]),
                retail_price=_optional_float(row.get("retail_price")),
                wholesale_price=_optional_float(row.get("wholesale_price")),
                settlement_price=_optional_float(row.get("settlement_price")),
                volume=_optional_float(row.get("volume")),
                source=row.get("source", "cached"),
                raw=row.get("raw") if isinstance(row.get("raw"), dict) else {},
            )
        )
    return prices


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
