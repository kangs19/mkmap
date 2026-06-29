from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.events import MidtermForecastConnector, TyphoonConnector, WeatherAlertConnector
from mkmap_meta.connectors.normalizers import public_api_error
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import dated_path, write_json


CONNECTORS = {
    "weather_alert": WeatherAlertConnector,
    "typhoon": TyphoonConnector,
    "midterm_forecast": MidtermForecastConnector,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live KMA event features and raw payloads.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--services", nargs="*", default=sorted(CONNECTORS), choices=sorted(CONNECTORS))
    return parser.parse_args()


def collect_service(service_code: str, target_date: date) -> dict[str, object]:
    connector = CONNECTORS[service_code]()
    payload = connector.fetch_payload(target_date)
    api_error = public_api_error(payload)
    features = [] if api_error else connector.normalize_payload(payload, target_date)

    write_json(dated_path("raw", service_code, target_date), payload)
    write_json(dated_path("features", service_code, target_date), features)

    return {
        "service": service_code,
        "ok": api_error is None,
        "api_error": api_error,
        "feature_count": len(features),
        "raw_path": str(dated_path("raw", service_code, target_date).relative_to(REPO_ROOT)),
        "feature_path": str(dated_path("features", service_code, target_date).relative_to(REPO_ROOT)),
    }


def main() -> int:
    ensure_env_loaded()
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    results = [collect_service(service_code, target_date) for service_code in args.services]
    write_json(dated_path("features", "event_collection_summary", target_date), results)
    print_json = __import__("json").dumps
    print(print_json(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

