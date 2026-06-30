from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV
from mkmap_meta.connectors.normalizers import public_api_error
from mkmap_meta.connectors.weather import RdaAgriWeatherConnector, _xml_to_payload
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import encode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test live RDA agri-weather observation calls.")
    parser.add_argument("--item", default="cabbage")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when env is missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)

    missing = [name for name in [DATA_GO_KR_API_KEY_ENV] if not os.getenv(name)]
    if missing:
        print(json.dumps({"ok": False, "reason": "missing_required_env", "missing": missing}, ensure_ascii=False, indent=2))
        return 2 if args.strict else 0

    connector = RdaAgriWeatherConnector()
    params = connector.build_params(args.item, target_date)
    payload: Any = connector.client.get(connector.service, connector.operation_path, **params)
    if isinstance(payload, str) and payload.lstrip().startswith("<"):
        payload = _xml_to_payload(payload)
    api_error = public_api_error(payload)
    features = [] if api_error else connector.fetch_weather(args.item, target_date)
    print(
        json.dumps(
            {
                "ok": bool(features),
                "item": args.item,
                "date": target_date.isoformat(),
                "api_error": api_error,
                "feature_count": len(features),
                "sample": encode(features[: args.max_rows]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if features or api_error else 1


if __name__ == "__main__":
    sys.exit(main())
