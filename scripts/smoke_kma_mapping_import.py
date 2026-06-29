from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
TMP_CSV = REPO_ROOT / "config" / "external_mappings" / "_tmp_kma_mapping_smoke.csv"

from scripts.import_kma_crop_weather_mapping import build_mapping, read_mapping_rows


def write_tmp_csv() -> None:
    TMP_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TMP_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
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
        writer.writerow(
            {
                "item_code": "radish",
                "item_name": "무",
                "candidate_region": "sample",
                "pa_crop_spe_id": "PA020101",
                "area_id": "4827000001",
                "area_name": "sample area",
                "mapping_status": "verified",
                "notes": "smoke test only",
            }
        )


def main() -> int:
    try:
        write_tmp_csv()
        grouped = read_mapping_rows(TMP_CSV)
        mapping = build_mapping(grouped["radish"])
        if mapping["mapping_status"] != "verified":
            raise RuntimeError(f"expected verified, got {mapping['mapping_status']}")
        if mapping["pa_crop_spe_id"] != "PA020101":
            raise RuntimeError("pa_crop_spe_id was not parsed")
        if len(mapping["area_ids"]) != 1:
            raise RuntimeError("area_id was not parsed")
        print(
            json.dumps(
                {
                    "item_code": "radish",
                    "mapping_status": mapping["mapping_status"],
                    "pa_crop_spe_id": mapping["pa_crop_spe_id"],
                    "area_id_count": len(mapping["area_ids"]),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        if TMP_CSV.exists():
            TMP_CSV.unlink()


if __name__ == "__main__":
    sys.exit(main())
