from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.production import KosisProductionConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, encode, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live KOSIS production features for mapped items.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--lookback", type=int, default=5)
    parser.add_argument("--items", nargs="*", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)
    target_year = args.year or target_date.year
    if not os.getenv("KOSIS_API_KEY"):
        payload = {
            "ok": False,
            "reason": "missing_required_env",
            "missing": ["KOSIS_API_KEY"],
            "feature_files": [],
        }
        out_path = dated_path("features", "kosis_production_collection_summary", target_date)
        write_json(out_path, payload)
        print(json.dumps(payload | {"summary_path": str(out_path)}, ensure_ascii=False, indent=2))
        return 2

    registry = default_registry()
    item_codes = args.items or sorted(registry.all_items())
    connector = KosisProductionConnector(registry=registry)
    summaries = []

    for item_code in item_codes:
        features = []
        used_year = None
        for year in range(target_year, target_year - args.lookback, -1):
            features = connector.fetch_production(item_code, year)
            if features:
                used_year = year
                break

        out_path = dated_path("features", f"kosis_production_{item_code}", target_date)
        write_json(out_path, features)
        summaries.append(
            {
                "item_code": item_code,
                "requested_year": target_year,
                "used_year": used_year,
                "feature_count": len(features),
                "feature_path": str(out_path),
            }
        )

    payload = {
        "ok": all(item["feature_count"] > 0 for item in summaries),
        "target_date": target_date.isoformat(),
        "items": summaries,
    }
    summary_path = dated_path("features", "kosis_production_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps(encode(payload | {"summary_path": str(summary_path)}), ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
