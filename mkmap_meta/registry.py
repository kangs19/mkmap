from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ENGINE_WEIGHTS = {
    "market_pressure": 0.35,
    "weather_pressure": 0.25,
    "production_region_weight": 0.15,
    "disaster_event_pressure": 0.15,
    "forecast_context": 0.10,
}

RISK_WEIGHT_ALIASES = {
    "event_pressure": "disaster_event_pressure",
}


@dataclass(frozen=True)
class ItemEnginePlan:
    item_code: str
    item_name: str
    engines: list[str]
    source_coverage: dict[str, Any]
    risk_weights: dict[str, Any]
    critical_weather_factors: list[str]
    manual_review_required: bool


class ItemMetadataRegistry:
    """Loads item metadata and prepares feature-engine plans.

    New items should be added as JSON files under metadata/items.
    The engine plan is derived from metadata rather than hard-coded by item.
    """

    def __init__(self, items_dir: Path | str) -> None:
        self.items_dir = Path(items_dir)
        self._items: dict[str, dict[str, Any]] | None = None

    def all_items(self) -> dict[str, dict[str, Any]]:
        if self._items is None:
            items: dict[str, dict[str, Any]] = {}
            for path in sorted(self.items_dir.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                item_code = data["item_code"]
                if item_code in items:
                    raise ValueError(f"Duplicate item_code: {item_code}")
                items[item_code] = data
            self._items = items
        return self._items

    def get_item(self, item_code: str) -> dict[str, Any]:
        try:
            return self.all_items()[item_code]
        except KeyError as exc:
            known = ", ".join(sorted(self.all_items()))
            raise KeyError(f"Unknown item_code={item_code!r}. Known items: {known}") from exc

    def build_engine_plan(self, item_code: str) -> ItemEnginePlan:
        item = self.get_item(item_code)
        overrides = item["feature_engine_profile"].get("feature_overrides", {})
        risk_overrides = overrides.get("risk_signal", {})

        risk_weights = dict(DEFAULT_ENGINE_WEIGHTS)
        for key, value in risk_overrides.items():
            if key.endswith("_weight"):
                normalized_key = key.removesuffix("_weight")
                normalized_key = RISK_WEIGHT_ALIASES.get(normalized_key, normalized_key)
                risk_weights[normalized_key] = value
            else:
                risk_weights[key] = value

        weather_factors: set[str] = set()
        for window in item["weather_profile"]["critical_windows"]:
            weather_factors.update(window["risk_factors"])

        return ItemEnginePlan(
            item_code=item["item_code"],
            item_name=item["item_name"],
            engines=item["feature_engine_profile"]["engine_set"],
            source_coverage=item["source_coverage"],
            risk_weights=risk_weights,
            critical_weather_factors=sorted(weather_factors),
            manual_review_required=item["source_coverage"]["manual_review_required"],
        )

    def build_all_engine_plans(self) -> dict[str, ItemEnginePlan]:
        return {
            item_code: self.build_engine_plan(item_code)
            for item_code in sorted(self.all_items())
        }


def default_registry() -> ItemMetadataRegistry:
    repo_root = Path(__file__).resolve().parents[1]
    return ItemMetadataRegistry(repo_root / "metadata" / "items")
