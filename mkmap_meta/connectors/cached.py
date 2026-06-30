from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from mkmap_meta.connectors.base import EventConnector, PriceConnector, ProductionConnector, WeatherConnector
from mkmap_meta.connectors.production import ManualProductionConnector
from mkmap_meta.models import EventFeature, PriceFeature, ProductionFeature, WeatherFeature
from mkmap_meta.storage import dated_path, read_json


class CachedEventConnector(EventConnector):
    def __init__(self, services: list[str] | None = None) -> None:
        self.services = services or [
            "impact_forecast",
            "midterm_forecast",
            "satellite",
            "typhoon",
            "weather_alert",
            "weather_chart",
        ]

    def fetch_events(self, target_date: date) -> list[EventFeature]:
        events: list[EventFeature] = []
        for service in self.services:
            path = dated_path("features", service, target_date)
            if path.exists():
                events.extend(_load_events(path))
        return events


class CachedPriceConnector(PriceConnector):
    def __init__(self, source_names: list[str] | None = None) -> None:
        self.source_names = source_names or ["kamis_price", "at_regional_price", "at_market_settlement"]

    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        prices: list[PriceFeature] = []
        for source_name in self.source_names:
            path = dated_path("features", f"{source_name}_{item_code}", target_date)
            if path.exists():
                prices.extend(_load_prices(path))
        return prices


class CachedProductionConnector(ProductionConnector):
    def __init__(self, source_names: list[str] | None = None) -> None:
        self.source_names = source_names or ["kosis_production"]

    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        production: list[ProductionFeature] = []
        target_date = date(year, 12, 31)
        for source_name in self.source_names:
            path = dated_path("features", f"{source_name}_{item_code}", target_date)
            if path.exists():
                production.extend(_load_production(path))

            latest_path = _latest_feature_path(f"{source_name}_{item_code}", year)
            if latest_path and latest_path != path:
                production.extend(_load_production(latest_path))
        return _dedupe_production(production)


class CachedWeatherConnector(WeatherConnector):
    def __init__(self, source_names: list[str] | None = None) -> None:
        self.source_names = source_names or ["kma_crop_weather"]

    def fetch_weather(self, item_code: str, target_date: date) -> list[WeatherFeature]:
        weather: list[WeatherFeature] = []
        for source_name in self.source_names:
            path = dated_path("features", f"{source_name}_{item_code}", target_date)
            if path.exists():
                weather.extend(_load_weather(path))
        return weather


class CachedOrManualProductionConnector(ProductionConnector):
    def __init__(self) -> None:
        self.cached = CachedProductionConnector()
        self.manual = ManualProductionConnector()

    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        cached = self.cached.fetch_production(item_code, year)
        if cached:
            return cached
        return self.manual.fetch_production(item_code, year)


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


def _load_production(path: Path) -> list[ProductionFeature]:
    rows = read_json(path)
    if not isinstance(rows, list):
        return []

    production: list[ProductionFeature] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        production.append(
            ProductionFeature(
                item_code=row["item_code"],
                region_code=row["region_code"],
                region_name=row["region_name"],
                year=int(row["year"]),
                cultivation_area=_optional_float(row.get("cultivation_area")),
                production_volume=_optional_float(row.get("production_volume")),
                production_share=_optional_float(row.get("production_share")),
                source=row.get("source", "cached"),
                raw=row.get("raw") if isinstance(row.get("raw"), dict) else {},
            )
        )
    return production


def _load_weather(path: Path) -> list[WeatherFeature]:
    rows = read_json(path)
    if not isinstance(rows, list):
        return []

    weather: list[WeatherFeature] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        weather.append(
            WeatherFeature(
                item_code=row["item_code"],
                region_code=str(row.get("region_code") or ""),
                base_date=date.fromisoformat(row["base_date"]),
                temperature=_optional_float(row.get("temperature")),
                rainfall=_optional_float(row.get("rainfall")),
                humidity=_optional_float(row.get("humidity")),
                wind_speed=_optional_float(row.get("wind_speed")),
                sunshine=_optional_float(row.get("sunshine")),
                source=row.get("source", "cached"),
                raw=row.get("raw") if isinstance(row.get("raw"), dict) else {},
            )
        )
    return weather


def _latest_feature_path(name: str, year: int) -> Path | None:
    base = Path(__file__).resolve().parents[2] / "data" / "features"
    if not base.exists():
        return None
    candidates = sorted(
        path / f"{name}.json"
        for path in base.iterdir()
        if path.is_dir() and path.name.startswith(str(year))
    )
    existing = [path for path in candidates if path.exists()]
    return existing[-1] if existing else None


def _dedupe_production(features: list[ProductionFeature]) -> list[ProductionFeature]:
    deduped: list[ProductionFeature] = []
    seen: set[tuple[str, str, int]] = set()
    for feature in features:
        key = (feature.item_code, feature.region_code, feature.year)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(feature)
    return deduped


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
