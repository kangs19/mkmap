from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"
DEFAULT_CSV = REPO_ROOT / "config" / "external_mappings" / "kma_crop_weather_template.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import KMA crop weather mapping codes into item metadata.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="CSV file with item_code, pa_crop_spe_id, area_id rows")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this, only preview.")
    return parser.parse_args()


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def read_mapping_rows(path: Path) -> dict[str, list[dict[str, str | None]]]:
    grouped: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"item_code", "candidate_region", "pa_crop_spe_id", "area_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

        for row in reader:
            item_code = clean(row.get("item_code"))
            if not item_code:
                continue
            grouped[item_code].append({key: clean(value) for key, value in row.items()})
    return grouped


def load_item(item_code: str) -> tuple[Path, dict[str, Any]]:
    path = ITEMS_DIR / f"{item_code}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown item_code in CSV: {item_code}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def build_mapping(rows: list[dict[str, str | None]]) -> dict[str, Any]:
    candidate_regions = [row["candidate_region"] for row in rows if row.get("candidate_region")]
    area_rows = [
        {
            "area_id": row["area_id"],
            "area_name": row.get("area_name") or row.get("candidate_region"),
        }
        for row in rows
        if row.get("area_id")
    ]
    area_ids = [row["area_id"] for row in area_rows if row.get("area_id")]
    crop_ids = sorted({row["pa_crop_spe_id"] for row in rows if row.get("pa_crop_spe_id")})

    mapping_status = "verified" if crop_ids and area_ids else "candidate_regions_only"
    if len(crop_ids) > 1:
        mapping_status = "candidate_regions_only"

    notes = "; ".join(sorted({row["notes"] for row in rows if row.get("notes")})) or None

    return {
        "mapping_status": mapping_status,
        "pa_crop_spe_id": crop_ids[0] if len(crop_ids) == 1 else None,
        "area_ids": area_ids,
        "area_mappings": area_rows,
        "candidate_regions": candidate_regions,
        "notes": notes or "KMA 활용가이드 코드표 기준으로 갱신",
    }


def update_item(item: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    external = item.setdefault("external_mappings", {})
    external["kma_crop_weather"] = mapping
    return item


def main() -> int:
    args = parse_args()
    grouped = read_mapping_rows(Path(args.csv))
    preview: list[dict[str, Any]] = []

    for item_code, rows in sorted(grouped.items()):
        path, item = load_item(item_code)
        mapping = build_mapping(rows)
        preview.append(
            {
                "item_code": item_code,
                "item_name": item["item_name"],
                "mapping_status": mapping["mapping_status"],
                "pa_crop_spe_id": mapping["pa_crop_spe_id"],
                "area_id_count": len(mapping["area_ids"]),
                "candidate_region_count": len(mapping["candidate_regions"]),
            }
        )
        if args.apply:
            updated = update_item(item, mapping)
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"applied": args.apply, "items": preview}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)

