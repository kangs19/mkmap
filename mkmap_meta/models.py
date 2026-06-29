from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class PriceFeature:
    item_code: str
    region_code: str | None
    base_date: date
    retail_price: float | None = None
    wholesale_price: float | None = None
    settlement_price: float | None = None
    volume: float | None = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductionFeature:
    item_code: str
    region_code: str
    region_name: str
    year: int
    cultivation_area: float | None = None
    production_volume: float | None = None
    production_share: float | None = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WeatherFeature:
    item_code: str
    region_code: str
    base_date: date
    temperature: float | None = None
    rainfall: float | None = None
    humidity: float | None = None
    wind_speed: float | None = None
    sunshine: float | None = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventFeature:
    region_code: str | None
    base_date: date
    event_type: str
    level: str | None = None
    title: str | None = None
    description: str | None = None
    severity_score: float | None = None
    source: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemFeatureBundle:
    item_code: str
    base_date: date
    prices: list[PriceFeature] = field(default_factory=list)
    production: list[ProductionFeature] = field(default_factory=list)
    weather: list[WeatherFeature] = field(default_factory=list)
    events: list[EventFeature] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

