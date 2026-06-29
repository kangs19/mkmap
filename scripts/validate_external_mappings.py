from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"


def load_item(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_kma_crop_weather(path: Path, item: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    mapping = item.get("external_mappings", {}).get("kma_crop_weather")
    if not mapping:
        errors.append(f"{path.name}: missing external_mappings.kma_crop_weather")
        return errors

    status = mapping.get("mapping_status")
    if status not in {"candidate_regions_only", "verified"}:
        errors.append(f"{path.name}: invalid kma_crop_weather mapping_status={status!r}")

    if status == "candidate_regions_only" and not mapping.get("candidate_regions"):
        errors.append(f"{path.name}: candidate_regions_only requires candidate_regions")

    if status == "verified":
        has_single_crop_id = bool(mapping.get("pa_crop_spe_id"))
        has_row_crop_ids = all(row.get("pa_crop_spe_id") for row in mapping.get("area_mappings", []))
        if not has_single_crop_id and not has_row_crop_ids:
            errors.append(f"{path.name}: verified mapping requires pa_crop_spe_id or per-row area_mappings.pa_crop_spe_id")
        if not mapping.get("area_ids"):
            errors.append(f"{path.name}: verified mapping requires area_ids")

    return errors


def main() -> int:
    errors: list[str] = []
    for path in sorted(ITEMS_DIR.glob("*.json")):
        item = load_item(path)
        errors.extend(validate_kma_crop_weather(path, item))

    if errors:
        print("External mapping validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"External mapping validation passed: {len(list(ITEMS_DIR.glob('*.json')))} item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

