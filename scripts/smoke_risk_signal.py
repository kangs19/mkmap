from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.engines.risk_signal import build_region_risk_signals
from mkmap_meta.factory import build_default_pipeline
from mkmap_meta.models import EventFeature, ItemFeatureBundle, PriceFeature, WeatherFeature


def encode(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, list):
        return [encode(inner) for inner in value]
    if isinstance(value, dict):
        return {key: encode(inner) for key, inner in value.items()}
    return value


def main() -> None:
    target_date = date(2026, 6, 29)
    base_bundle = build_default_pipeline().build_item_bundle("cabbage", target_date)
    prices = [
        PriceFeature("cabbage", None, target_date, wholesale_price=3600, source="sample"),
        PriceFeature("cabbage", None, target_date - timedelta(days=1), wholesale_price=2800, source="sample"),
        PriceFeature("cabbage", None, target_date - timedelta(days=2), wholesale_price=2750, source="sample"),
        PriceFeature("cabbage", None, target_date - timedelta(days=3), wholesale_price=2700, source="sample"),
    ]
    weather = [
        WeatherFeature("cabbage", "42", target_date, temperature=31.5, rainfall=72, humidity=86, source="sample")
    ]
    events = [
        EventFeature("42", target_date, "weather_alert", level="경보", title="호우경보", source="sample")
    ]
    bundle = ItemFeatureBundle(
        item_code=base_bundle.item_code,
        base_date=base_bundle.base_date,
        prices=prices,
        production=base_bundle.production,
        weather=weather,
        events=events,
        metadata=base_bundle.metadata,
    )
    signals = build_region_risk_signals(bundle)
    print(json.dumps(encode(signals), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
