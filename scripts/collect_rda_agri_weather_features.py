from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV
from mkmap_meta.connectors.weather import RdaAgriWeatherConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect RDA agricultural weather monthly observation features.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Cache date / end month, YYYY-MM-DD")
    parser.add_argument("--months-back", type=int, default=1)
    parser.add_argument("--items", nargs="*", default=None)
    return parser.parse_args()


def main() -> int:
    ensure_env_loaded()
    if not os.getenv(DATA_GO_KR_API_KEY_ENV):
        print(json.dumps({"ok": False, "reason": "missing_env", "missing": [DATA_GO_KR_API_KEY_ENV]}, ensure_ascii=False, indent=2))
        return 1

    args = parse_args()
    target_date = date.fromisoformat(args.date)
    item_codes = args.items or sorted(default_registry().all_items())
    connector = RdaAgriWeatherConnector()

    summaries = []
    for item_code in item_codes:
        features = []
        for month_date in _month_starts(target_date, args.months_back):
            features.extend(connector.fetch_weather(item_code, month_date))

        deduped = _dedupe_features(features)
        out_path = dated_path("features", f"rda_agri_weather_{item_code}", target_date)
        write_json(out_path, deduped)
        summaries.append(
            {
                "source": "rda_agri_weather",
                "item_code": item_code,
                "feature_count": len(deduped),
                "date_min": min((feature.base_date.isoformat() for feature in deduped), default=None),
                "date_max": max((feature.base_date.isoformat() for feature in deduped), default=None),
                "feature_path": str(out_path),
            }
        )

    payload = {
        "ok": any(row["feature_count"] for row in summaries),
        "target_date": target_date.isoformat(),
        "months_back": args.months_back,
        "items": item_codes,
        "sources": summaries,
    }
    summary_path = dated_path("features", "rda_agri_weather_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps({**payload, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _month_starts(target_date: date, months_back: int) -> list[date]:
    year = target_date.year
    month = target_date.month
    starts = []
    for _ in range(max(months_back, 1)):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(starts))


def _dedupe_features(features: list[object]) -> list[object]:
    deduped = []
    seen = set()
    for feature in features:
        key = (
            getattr(feature, "item_code", None),
            getattr(feature, "region_code", None),
            getattr(feature, "base_date", None),
            getattr(feature, "source", None),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(feature)
    return deduped


if __name__ == "__main__":
    sys.exit(main())
