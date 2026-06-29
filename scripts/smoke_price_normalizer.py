from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.price import normalize_price_rows


def main() -> None:
    sample_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "item_code": "cabbage",
                            "region_code": "42",
                            "date": "20260629",
                            "retail_price": "3,200",
                            "wholesale_price": "2,400",
                            "volume": "120.5"
                        }
                    ]
                }
            }
        }
    }

    features = normalize_price_rows(
        sample_payload,
        item_code="cabbage",
        default_date=date(2026, 6, 29),
        source="sample",
    )
    print(json.dumps([feature.__dict__ | {"base_date": feature.base_date.isoformat()} for feature in features], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
