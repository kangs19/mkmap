from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from mkmap_meta.engines.risk_signal import RegionRiskSignal, build_region_risk_signals
from mkmap_meta.factory import build_default_pipeline
from mkmap_meta.pipeline import ItemFeaturePipeline
from mkmap_meta.registry import ItemMetadataRegistry, default_registry


class SignalService:
    """API-facing service for item and today risk signals."""

    def __init__(
        self,
        pipeline: ItemFeaturePipeline | None = None,
        registry: ItemMetadataRegistry | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.pipeline = pipeline or build_default_pipeline()

    def get_item_signals(self, item_code: str, target_date: date | None = None) -> dict[str, Any]:
        target_date = target_date or date.today()
        item = self.registry.get_item(item_code)
        bundle = self.pipeline.build_item_bundle(item_code, target_date)
        signals = build_region_risk_signals(bundle)
        return {
            "item_code": item_code,
            "item_name": item["item_name"],
            "base_date": target_date.isoformat(),
            "signals": [_encode_signal(signal) for signal in signals],
            "data_status": _data_status(bundle),
        }

    def get_today_signals(self, target_date: date | None = None) -> dict[str, Any]:
        target_date = target_date or date.today()
        items: list[dict[str, Any]] = []
        for item_code in sorted(self.registry.all_items()):
            response = self.get_item_signals(item_code, target_date)
            top_signal = response["signals"][0] if response["signals"] else None
            items.append(
                {
                    "item_code": response["item_code"],
                    "item_name": response["item_name"],
                    "top_signal": top_signal,
                    "signal_count": len(response["signals"]),
                    "data_status": response["data_status"],
                }
            )

        return {
            "base_date": target_date.isoformat(),
            "items": sorted(
                items,
                key=lambda item: item["top_signal"]["risk_score"] if item["top_signal"] else 0,
                reverse=True,
            ),
        }


def _encode_signal(signal: RegionRiskSignal) -> dict[str, Any]:
    return _encode(signal)


def _encode(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return _encode(asdict(value))
    if isinstance(value, list):
        return [_encode(inner) for inner in value]
    if isinstance(value, dict):
        return {key: _encode(inner) for key, inner in value.items()}
    return value


def _data_status(bundle: Any) -> dict[str, Any]:
    return {
        "price_features": len(bundle.prices),
        "production_features": len(bundle.production),
        "weather_features": len(bundle.weather),
        "event_features": len(bundle.events),
        "has_price_data": bool(bundle.prices),
        "has_weather_data": bool(bundle.weather),
        "has_event_data": bool(bundle.events),
    }

