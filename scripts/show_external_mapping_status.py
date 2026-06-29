from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"


def load_items() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(ITEMS_DIR.glob("*.json"))
    ]


def main() -> int:
    rows = []
    for item in load_items():
        mapping = item.get("external_mappings", {}).get("kma_crop_weather", {})
        rows.append(
            {
                "item_code": item["item_code"],
                "item_name": item["item_name"],
                "provider": "kma_crop_weather",
                "mapping_status": mapping.get("mapping_status", "missing"),
                "has_pa_crop_spe_id": bool(mapping.get("pa_crop_spe_id")),
                "area_id_count": len(mapping.get("area_ids", [])),
                "candidate_regions": mapping.get("candidate_regions", []),
                "notes": mapping.get("notes"),
            }
        )

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

