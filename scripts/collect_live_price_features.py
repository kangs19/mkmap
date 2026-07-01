from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.price import AtMarketSettlementConnector, AtRegionalPriceConnector, KamisPriceConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, encode, write_json


CONNECTORS = {
    "at_market_settlement": {
        "factory": AtMarketSettlementConnector,
        "required_env": ["DATA_GO_KR_API_KEY"],
    },
    "at_regional_price": {
        "factory": AtRegionalPriceConnector,
        "required_env": ["DATA_GO_KR_API_KEY"],
    },
    "kamis_price": {
        "factory": KamisPriceConnector,
        "required_env": ["KAMIS_API_KEY"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect live price features for mapped items.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--items", nargs="*", default=None)
    parser.add_argument("--services", nargs="*", default=sorted(CONNECTORS), choices=sorted(CONNECTORS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)
    registry = default_registry()
    item_codes = args.items or sorted(registry.all_items())

    active_services = []
    skipped_services = []
    for service_code in args.services:
        missing = [e for e in CONNECTORS[service_code]["required_env"] if not os.getenv(e)]
        if missing:
            print(f"[WARN] Skipping {service_code}: missing env {missing}", file=sys.stderr)
            skipped_services.append({"service": service_code, "missing_env": missing})
        else:
            active_services.append(service_code)

    if not active_services:
        all_missing = sorted({e for s in args.services for e in CONNECTORS[s]["required_env"] if not os.getenv(e)})
        payload = {
            "ok": False,
            "reason": "missing_required_env",
            "missing": all_missing,
            "feature_files": [],
        }
        out_path = dated_path("features", "price_collection_summary", target_date)
        write_json(out_path, payload)
        print(json.dumps(payload | {"summary_path": str(out_path)}, ensure_ascii=False, indent=2))
        return 2

    summaries = []
    for service_code in active_services:
        connector = CONNECTORS[service_code]["factory"](registry=registry)
        for item_code in item_codes:
            api_error = None
            prices = []
            try:
                prices = connector.fetch_prices(item_code, target_date, days_back=args.days_back)
            except HTTPError as exc:
                api_error = {"resultCode": f"HTTP_{exc.code}", "resultMsg": exc.reason}
            except URLError as exc:
                api_error = {"resultCode": "URL_ERROR", "resultMsg": str(exc.reason)}

            out_path = dated_path("features", f"{service_code}_{item_code}", target_date)
            write_json(out_path, prices)
            summaries.append(
                {
                    "service": service_code,
                    "item_code": item_code,
                    "ok": api_error is None,
                    "api_error": api_error,
                    "feature_count": len(prices),
                    "feature_path": str(out_path),
                }
            )

    payload = {
        "ok": all(item["ok"] for item in summaries),
        "target_date": target_date.isoformat(),
        "days_back": args.days_back,
        "services": active_services,
        "skipped_services": skipped_services,
        "items": summaries,
    }
    summary_path = dated_path("features", "price_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps(encode(payload | {"summary_path": str(summary_path)}), ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
