from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.normalizers import public_api_error
from mkmap_meta.connectors.weather import CropMainAreaWeatherConnector, normalize_weather_rows
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live KMA crop main-area weather features.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--items", nargs="*", help="Item codes. Defaults to all registered items.")
    parser.add_argument("--lookback-days", type=int, default=0, help="Try previous dates when the target date has no rows.")
    return parser.parse_args()


def collect_item(connector: CropMainAreaWeatherConnector, item_code: str, target_date: date, lookback_days: int) -> dict[str, Any]:
    attempts = [target_date - timedelta(days=offset) for offset in range(lookback_days + 1)]
    raw_payloads: list[dict[str, Any]] = []

    for attempted_date in attempts:
        features = []
        errors = []
        param_sets = connector.build_param_sets(item_code, attempted_date)
        for params in param_sets:
            payload = connector.client.get(connector.service, connector.operation_path, **params)
            error = public_api_error(payload)
            raw_payloads.append({"date": attempted_date.isoformat(), "params": params, "payload": payload})
            if error:
                errors.append(error)
                continue
            features.extend(
                normalize_weather_rows(
                    payload,
                    item_code=item_code,
                    default_date=attempted_date,
                    source=connector.service.name,
                )
            )

        if features or attempted_date == attempts[-1]:
            write_json(dated_path("raw", f"kma_crop_weather_{item_code}", target_date), raw_payloads)
            write_json(dated_path("features", f"kma_crop_weather_{item_code}", target_date), features)
            return {
                "item_code": item_code,
                "target_date": target_date.isoformat(),
                "used_date": attempted_date.isoformat(),
                "feature_count": len(features),
                "param_count": len(param_sets),
                "error_count": len(errors),
                "raw_path": str(dated_path("raw", f"kma_crop_weather_{item_code}", target_date).relative_to(REPO_ROOT)),
                "feature_path": str(dated_path("features", f"kma_crop_weather_{item_code}", target_date).relative_to(REPO_ROOT)),
            }

    raise RuntimeError("unreachable")


def main() -> int:
    ensure_env_loaded()
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    registry = default_registry()
    item_codes = args.items or sorted(registry.all_items())
    connector = CropMainAreaWeatherConnector()

    results = [collect_item(connector, item_code, target_date, args.lookback_days) for item_code in item_codes]
    write_json(dated_path("features", "kma_crop_weather_collection_summary", target_date), results)

    import json

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
