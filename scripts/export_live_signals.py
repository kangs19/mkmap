from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.cached import CachedEventConnector, CachedOrManualProductionConnector, CachedWeatherConnector
from mkmap_meta.engines.risk_signal import build_region_risk_signals
from mkmap_meta.factory import build_default_pipeline
from mkmap_meta.pipeline import ItemFeaturePipeline
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and store live-backed risk signals.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--live-events", action="store_true", help="Call event APIs directly instead of using cached event features")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    pipeline = build_default_pipeline() if args.live_events else ItemFeaturePipeline(
        production_connectors=[CachedOrManualProductionConnector()],
        weather_connectors=[CachedWeatherConnector()],
        event_connectors=[CachedEventConnector()],
    )
    registry = default_registry()

    payload = []
    for item_code in sorted(registry.all_items()):
        bundle = pipeline.build_item_bundle(item_code, target_date)
        signals = build_region_risk_signals(bundle)
        payload.append(
            {
                "item_code": item_code,
                "item_name": registry.get_item(item_code)["item_name"],
                "base_date": target_date,
                "data_status": {
                    "prices": len(bundle.prices),
                    "production": len(bundle.production),
                    "weather": len(bundle.weather),
                    "events": len(bundle.events),
                },
                "signals": signals,
            }
        )

    out_path = dated_path("signals", "region_risk_signals", target_date)
    write_json(out_path, payload)
    print(f"Exported {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
