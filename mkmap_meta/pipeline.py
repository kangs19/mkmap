from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Iterable

from mkmap_meta.connectors.base import EventConnector, PriceConnector, ProductionConnector, WeatherConnector
from mkmap_meta.models import ItemFeatureBundle
from mkmap_meta.registry import ItemMetadataRegistry, default_registry


class ItemFeaturePipeline:
    """Builds normalized feature bundles for item-level risk engines."""

    def __init__(
        self,
        registry: ItemMetadataRegistry | None = None,
        price_connectors: Iterable[PriceConnector] = (),
        production_connectors: Iterable[ProductionConnector] = (),
        weather_connectors: Iterable[WeatherConnector] = (),
        event_connectors: Iterable[EventConnector] = (),
    ) -> None:
        self.registry = registry or default_registry()
        self.price_connectors = list(price_connectors)
        self.production_connectors = list(production_connectors)
        self.weather_connectors = list(weather_connectors)
        self.event_connectors = list(event_connectors)

    def build_item_bundle(self, item_code: str, target_date: date | None = None) -> ItemFeatureBundle:
        target_date = target_date or date.today()
        item = self.registry.get_item(item_code)
        plan = self.registry.build_engine_plan(item_code)

        prices = [
            feature
            for connector in self.price_connectors
            for feature in connector.fetch_prices(item_code, target_date)
        ]
        production = [
            feature
            for connector in self.production_connectors
            for feature in connector.fetch_production(item_code, target_date.year)
        ]
        weather = [
            feature
            for connector in self.weather_connectors
            for feature in connector.fetch_weather(item_code, target_date)
        ]
        events = [
            feature
            for connector in self.event_connectors
            for feature in connector.fetch_events(target_date)
        ]

        return ItemFeatureBundle(
            item_code=item_code,
            base_date=target_date,
            prices=prices,
            production=production,
            weather=weather,
            events=events,
            metadata={
                "item": item,
                "engine_plan": asdict(plan),
            },
        )

    def build_all_bundles(self, target_date: date | None = None) -> dict[str, ItemFeatureBundle]:
        return {
            item_code: self.build_item_bundle(item_code, target_date)
            for item_code in sorted(self.registry.all_items())
        }

