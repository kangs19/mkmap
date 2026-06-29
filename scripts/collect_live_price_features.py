from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.price import KamisPriceConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, encode, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live KAMIS price features for mapped items.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=14)
    parser.add_argument("--items", nargs="*", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)
    missing = [name for name in ["KAMIS_API_KEY"] if not os.getenv(name)]
    if missing:
        payload = {
            "ok": False,
            "reason": "missing_required_env",
            "missing": missing,
            "feature_files": [],
        }
        out_path = dated_path("features", "kamis_price_collection_summary", target_date)
        write_json(out_path, payload)
        print(json.dumps(payload | {"summary_path": str(out_path)}, ensure_ascii=False, indent=2))
        return 2

    registry = default_registry()
    item_codes = args.items or sorted(registry.all_items())
    connector = KamisPriceConnector(registry=registry)

    summaries = []
    for item_code in item_codes:
        prices = connector.fetch_prices(item_code, target_date, days_back=args.days_back)
        out_path = dated_path("features", f"kamis_price_{item_code}", target_date)
        write_json(out_path, prices)
        summaries.append(
            {
                "item_code": item_code,
                "feature_count": len(prices),
                "feature_path": str(out_path),
            }
        )

    payload = {
        "ok": all(item["feature_count"] > 0 for item in summaries),
        "target_date": target_date.isoformat(),
        "days_back": args.days_back,
        "items": summaries,
    }
    summary_path = dated_path("features", "kamis_price_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps(encode(payload | {"summary_path": str(summary_path)}), ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
