from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.production import normalize_production_rows


def main() -> None:
    sample_payload = [
        {
            "C1_NM": "배추",
            "C2_ID": "42",
            "C2_NM": "강원",
            "PRD_DE": "2025",
            "재배면적": "1,200",
            "DT": "3,000"
        },
        {
            "C1_NM": "배추",
            "C2_ID": "46",
            "C2_NM": "전남",
            "PRD_DE": "2025",
            "재배면적": "800",
            "DT": "1,000"
        }
    ]
    features = normalize_production_rows(sample_payload, item_code="cabbage", default_year=2025)
    print(json.dumps([asdict(feature) for feature in features], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
