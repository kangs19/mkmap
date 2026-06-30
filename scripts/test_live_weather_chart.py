from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.events import WeatherChartConnector
from mkmap_meta.env import ensure_env_loaded
from scripts.live_event_test import data_go_kr_required_env, run_live_event_test


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test live KMA weather chart calls.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when env is missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    return run_live_event_test(
        connector_factory=WeatherChartConnector,
        service_name="kma_weather_chart",
        target_date=date.fromisoformat(args.date),
        required_env=data_go_kr_required_env(),
        max_rows=args.max_rows,
        strict=args.strict,
    )


if __name__ == "__main__":
    sys.exit(main())
