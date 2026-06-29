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
from mkmap_meta.connectors.weather import CropMainAreaWeatherConnector
from mkmap_meta.registry import default_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test live KMA crop main-area weather calls.")
    parser.add_argument("--item", default="cabbage", help="Item code, e.g. cabbage")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=5)
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
        "has_pa_crop_spe_id": bool(mapping.get("pa_crop_spe_id")),
        "area_id_count": len(mapping.get("area_ids", [])),
        "candidate_regions": mapping.get("candidate_regions", []),
    }


def main() -> int:
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
    features = connector.fetch_weather(args.item, target_date)
    print(
        json.dumps(
            {
                "ok": True,
                "item_code": args.item,
                "date": target_date.isoformat(),
                "feature_count": len(features),
                "features": encode(features[: args.max_rows]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
