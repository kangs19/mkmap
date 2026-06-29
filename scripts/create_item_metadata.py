from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new MK-MAP item metadata draft.")
    parser.add_argument("item_code", help="Stable ASCII code, e.g. spinach")
    parser.add_argument("item_name", help="Display name, e.g. 시금치")
    parser.add_argument("--category", default="채소류")
    parser.add_argument("--storage-type", default="fresh")
    parser.add_argument("--region-code", default="manual")
    parser.add_argument("--region-name", default="검토 필요")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def validate_code(item_code: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", item_code):
        raise ValueError("item_code must match ^[a-z][a-z0-9_]*$")


def build_template(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "item_code": args.item_code,
        "item_name": args.item_name,
        "category": args.category,
        "aliases": [],
        "crop_profile": {
            "storage_type": args.storage_type,
            "cultivation_type": ["open_field"],
            "growth_calendar": {"default": []},
            "harvest_calendar": {"default": []},
            "demand_events": [],
            "substitute_items": [],
        },
        "production_profile": {
            "region_strategy": "manual_weighted",
            "manual_regions": [
                {
                    "region_code": args.region_code,
                    "region_name": args.region_name,
                    "base_weight": 1.0,
                    "notes": "신규 품목 등록 후 주산지와 가중치를 검토하세요.",
                }
            ],
        },
        "market_profile": {
            "price_volatility": "medium",
            "price_lag_days": 3,
            "market_sensitivity": {
                "retail_price": 0.35,
                "wholesale_price": 0.4,
                "settlement_volume": 0.25,
            },
        },
        "weather_profile": {
            "sensitivity": {
                "heat": 0.5,
                "cold": 0.5,
                "heavy_rain": 0.5,
                "drought": 0.5,
                "wind": 0.4,
                "humidity": 0.4,
            },
            "critical_windows": [
                {
                    "name": "default_growth",
                    "months": [],
                    "risk_factors": ["heat", "heavy_rain", "drought"],
                }
            ],
        },
        "event_profile": {
            "enabled_events": ["weather_alert", "impact_forecast", "typhoon", "midterm_forecast"],
            "event_weights": {
                "weather_alert": 0.35,
                "impact_forecast": 0.2,
                "typhoon": 0.3,
                "midterm_forecast": 0.15,
            },
        },
        "feature_engine_profile": {
            "engine_set": [
                "item_meta",
                "production_region",
                "price_market",
                "agri_weather",
                "disaster_event",
                "forecast_context",
                "risk_signal",
            ],
            "feature_overrides": {
                "risk_signal": {
                    "weather_pressure_weight": 0.25,
                    "event_pressure_weight": 0.15,
                }
            },
        },
        "source_coverage": {
            "kamis": True,
            "kosis": True,
            "data_go_kr": [
                "crop_weather",
                "agri_weather_observation",
                "weather_alert",
                "impact_forecast",
                "typhoon",
                "midterm_forecast",
            ],
            "manual_review_required": True,
        },
    }


def main() -> int:
    args = parse_args()
    validate_code(args.item_code)

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    path = ITEMS_DIR / f"{args.item_code}.json"
    if path.exists() and not args.overwrite:
        print(f"Refusing to overwrite existing file: {path}")
        return 1

    data = build_template(args)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {path}")
    print("Next: fill growth/harvest months, production regions, and weather sensitivities.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

