from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.events import WeatherAlertConnector
from mkmap_meta.connectors.normalizers import public_api_error
from mkmap_meta.env import ensure_env_loaded
from scripts.live_event_test import data_go_kr_required_env, encode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test live KMA weather alert calls.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=0, help="Also test previous N days.")
    parser.add_argument("--stn-ids", default="0", help="Comma-separated stnId values, e.g. 0,108,109")
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when env is missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    missing_env = [env_name for env_name in data_go_kr_required_env() if not os.getenv(env_name)]
    if missing_env:
        print(
            json.dumps(
                {
                    "ok": False,
                    "service": "kma_weather_alert",
                    "reason": "Missing required environment variable(s)",
                    "missing_env": missing_env,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if args.strict else 0

    target_date = date.fromisoformat(args.date)
    stn_ids = [part.strip() for part in args.stn_ids.split(",") if part.strip()]
    connector = WeatherAlertConnector()
    results: list[dict[str, Any]] = []
    events = []

    for offset in range(args.lookback_days + 1):
        current_date = target_date - timedelta(days=offset)
        for stn_id in stn_ids:
            params = connector.build_params(current_date)
            params[os.getenv("KMA_WEATHER_ALERT_STN_PARAM", "stnId")] = stn_id
            payload = connector.client.get(connector.service, connector.operation_path, **params)
            api_error = public_api_error(payload)
            normalized = [] if api_error else connector.normalize_payload(payload, current_date)
            events.extend(normalized)
            results.append(
                {
                    "date": current_date.isoformat(),
                    "stnId": stn_id,
                    "ok": api_error is None,
                    "api_error": api_error,
                    "event_count": len(normalized),
                }
            )

    ok_results = [result for result in results if result["ok"]]
    api_errors = [result for result in results if result["api_error"]]
    print(
        json.dumps(
            {
                "ok": bool(ok_results),
                "service": "kma_weather_alert",
                "date": target_date.isoformat(),
                "lookback_days": args.lookback_days,
                "stn_ids": stn_ids,
                "summary": {
                    "total_attempts": len(results),
                    "ok_attempts": len(ok_results),
                    "api_error_attempts": len(api_errors),
                    "event_count": len(events),
                },
                "attempts": results,
                "events": encode(events[: args.max_rows]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok_results or not args.strict else 1


if __name__ == "__main__":
    sys.exit(main())
