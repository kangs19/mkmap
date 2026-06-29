from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"
OUTPUT = REPO_ROOT / "config" / "external_mappings" / "kma_crop_weather_template.csv"


def load_items() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(ITEMS_DIR.glob("*.json"))
    ]


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "item_code",
                "item_name",
                "candidate_region",
                "pa_crop_spe_id",
                "area_id",
                "area_name",
                "mapping_status",
                "notes",
            ],
        )
        writer.writeheader()
        for item in load_items():
            mapping = item.get("external_mappings", {}).get("kma_crop_weather", {})
            for region in mapping.get("candidate_regions", []):
                writer.writerow(
                    {
                        "item_code": item["item_code"],
                        "item_name": item["item_name"],
                        "candidate_region": region,
                        "pa_crop_spe_id": mapping.get("pa_crop_spe_id") or "",
                        "area_id": "",
                        "area_name": "",
                        "mapping_status": mapping.get("mapping_status", "candidate_regions_only"),
                        "notes": mapping.get("notes", ""),
                    }
                )

    print(f"Exported {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

