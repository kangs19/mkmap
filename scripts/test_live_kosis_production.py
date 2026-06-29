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
from mkmap_meta.storage import encode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test KOSIS production integration.")
    parser.add_argument("--item", default="cabbage")
    parser.add_argument("--year", type=int, default=date.today().year - 1)
    parser.add_argument("--lookback", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    if not os.getenv("KOSIS_API_KEY"):
        print(json.dumps({"ok": False, "reason": "missing_required_env", "missing": ["KOSIS_API_KEY"]}, ensure_ascii=False, indent=2))
        return 2

    connector = KosisProductionConnector()
    features = []
    used_year = None
    for year in range(args.year, args.year - args.lookback, -1):
        features = connector.fetch_production(args.item, year)
        if features:
            used_year = year
            break

    print(
        json.dumps(
            {
                "ok": bool(features),
                "item": args.item,
                "requested_year": args.year,
                "used_year": used_year,
                "feature_count": len(features),
                "sample": encode(features[:5]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if features else 1


if __name__ == "__main__":
    sys.exit(main())
