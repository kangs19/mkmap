from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from mkmap_meta.models import EventFeature, PriceFeature, ProductionFeature, WeatherFeature


class PriceConnector(ABC):
    @abstractmethod
    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        raise NotImplementedError


class ProductionConnector(ABC):
    @abstractmethod
    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        raise NotImplementedError


class WeatherConnector(ABC):
    @abstractmethod
    def fetch_weather(self, item_code: str, target_date: date) -> list[WeatherFeature]:
        raise NotImplementedError


class EventConnector(ABC):
    @abstractmethod
    def fetch_events(self, target_date: date) -> list[EventFeature]:
        raise NotImplementedError

