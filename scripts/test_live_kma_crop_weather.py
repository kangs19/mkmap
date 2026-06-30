from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV
from mkmap_meta.connectors.normalizers import public_api_error
from mkmap_meta.connectors.weather import CropMainAreaWeatherConnector, normalize_weather_rows
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test live KMA crop main-area weather calls.")
    parser.add_argument("--item", default="cabbage", help="Item code, e.g. cabbage")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--max-requests", type=int, default=3, help="Limit live calls for diagnostics. Use 0 for all mappings.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when env or verified mapping is missing")
    return parser.parse_args()


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


def mapping_status(item_code: str) -> dict[str, Any]:
    item = default_registry().get_item(item_code)
    mapping = item.get("external_mappings", {}).get("kma_crop_weather", {})
    return {
        "mapping_status": mapping.get("mapping_status", "missing"),
        "has_pa_crop_spe_id": bool(mapping.get("pa_crop_spe_id") or mapping.get("pa_crop_spe_ids")),
        "area_id_count": len(mapping.get("area_ids", [])),
        "area_mapping_count": len(mapping.get("area_mappings", [])),
        "candidate_regions": mapping.get("candidate_regions", []),
    }


def main() -> int:
    ensure_env_loaded()
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    status = mapping_status(args.item)

    if not os.getenv(DATA_GO_KR_API_KEY_ENV):
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": f"Missing environment variable {DATA_GO_KR_API_KEY_ENV}",
                    "mapping": status,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if args.strict else 0

    if status["mapping_status"] != "verified":
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "KMA crop weather mapping is not verified yet. Fill pa_crop_spe_id and area_id first.",
                    "mapping": status,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if args.strict else 0

    connector = CropMainAreaWeatherConnector()
    param_sets = connector.build_param_sets(args.item, target_date)
    tested_param_sets = param_sets if args.max_requests <= 0 else param_sets[: args.max_requests]
    features = []
    api_errors = []
    for params in tested_param_sets:
        payload = connector.client.get(connector.service, connector.operation_path, **params)
        api_error = public_api_error(payload)
        if api_error:
            api_errors.append({"params": {key: value for key, value in params.items() if key != "serviceKey"}, "api_error": api_error})
            continue
        features.extend(
            normalize_weather_rows(
                payload,
                item_code=args.item,
                default_date=target_date,
                source=connector.service.name,
            )
        )

    print(
        json.dumps(
            {
                "ok": not api_errors,
                "item_code": args.item,
                "date": target_date.isoformat(),
                "total_param_sets": len(param_sets),
                "tested_param_sets": len(tested_param_sets),
                "feature_count": len(features),
                "api_errors": api_errors,
                "features": encode(features[: args.max_rows]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not api_errors else 1


if __name__ == "__main__":
    sys.exit(main())
