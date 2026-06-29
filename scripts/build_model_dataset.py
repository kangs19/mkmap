from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.cached import CachedEventConnector, CachedOrManualProductionConnector, CachedPriceConnector, CachedWeatherConnector
from mkmap_meta.connectors.production import ManualProductionConnector
from mkmap_meta.engines.risk_signal import build_region_risk_signals
from mkmap_meta.factory import build_default_pipeline
from mkmap_meta.pipeline import ItemFeaturePipeline
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a first-pass model dataset from feature bundles.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--live-events", action="store_true", help="Call event APIs directly instead of using cached event features")
    parser.add_argument("--live-prices", action="store_true", help="Call price APIs directly instead of using cached price features")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    registry = default_registry()
    if args.live_events or args.live_prices:
        pipeline = build_default_pipeline()
        if not args.live_events:
            pipeline.event_connectors = [CachedEventConnector()]
        if not args.live_prices:
            pipeline.price_connectors = [CachedPriceConnector()]
        pipeline.production_connectors = [CachedOrManualProductionConnector()]
        pipeline.weather_connectors = [CachedWeatherConnector()]
    else:
        pipeline = ItemFeaturePipeline(
            price_connectors=[CachedPriceConnector()],
            production_connectors=[CachedOrManualProductionConnector()],
            weather_connectors=[CachedWeatherConnector()],
            event_connectors=[CachedEventConnector()],
        )
    rows: list[dict[str, object]] = []

    for item_code in sorted(registry.all_items()):
        bundle = pipeline.build_item_bundle(item_code, target_date)
        signals = build_region_risk_signals(bundle)
        for signal in signals:
            rows.append(
                {
                    "base_date": target_date.isoformat(),
                    "item_code": signal.item_code,
                    "region_code": signal.region_code,
                    "region_name": signal.region_name,
                    "risk_score": signal.risk_score,
                    "risk_level": signal.risk_level,
                    "price_effect": signal.price_effect,
                    "top_factor_1": signal.top_factors[0].factor if signal.top_factors else "",
                    "top_factor_1_contribution": signal.top_factors[0].contribution if signal.top_factors else 0,
                    "price_feature_count": len(bundle.prices),
                    "weather_feature_count": len(bundle.weather),
                    "event_feature_count": len(bundle.events),
                    "target_next_price_change": "",
                }
            )

    out_path = data_dir() / "model" / f"price_prediction_dataset_{target_date:%Y%m%d}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {out_path.relative_to(REPO_ROOT)} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
