from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV
from mkmap_meta.connectors.price import AtMarketSettlementConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import encode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test aT public wholesale market settlement integration.")
    parser.add_argument("--item", default="onion")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=3)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when env is missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)

    missing = [name for name in [DATA_GO_KR_API_KEY_ENV] if not os.getenv(name)]
    if missing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "missing_required_env",
                    "missing": missing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if args.strict else 0

    connector = AtMarketSettlementConnector(registry=default_registry())
    prices = connector.fetch_prices(args.item, target_date, days_back=args.days_back)
    payload = {
        "ok": bool(prices),
        "item": args.item,
        "date_range": [(target_date - timedelta(days=args.days_back - 1)).isoformat(), target_date.isoformat()],
        "feature_count": len(prices),
        "sample": encode(prices[:3]),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if prices else 1


if __name__ == "__main__":
    sys.exit(main())
