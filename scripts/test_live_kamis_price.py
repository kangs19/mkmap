from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.price import KamisPriceConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import encode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test KAMIS periodProductList integration.")
    parser.add_argument("--item", default="cabbage")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)

    missing = [name for name in ["KAMIS_API_KEY"] if not os.getenv(name)]
    if missing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "missing_required_env",
                    "missing": missing,
                    "hint": "KAMIS periodProductList requires p_cert_key. p_cert_id uses KAMIS_CERT_ID or the mkmap fallback.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    connector = KamisPriceConnector(registry=default_registry())
    prices = connector.fetch_prices(args.item, target_date, days_back=args.days_back)
    print(
        json.dumps(
            {
                "ok": bool(prices),
                "item": args.item,
                "date_range": [(target_date - timedelta(days=args.days_back - 1)).isoformat(), target_date.isoformat()],
                "feature_count": len(prices),
                "sample": encode(prices[:3]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if prices else 1


if __name__ == "__main__":
    sys.exit(main())
