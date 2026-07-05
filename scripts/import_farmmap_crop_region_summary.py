from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.database import AsyncSessionLocal, init_db
from app.models.farmmap import FarmMapCropRegion, FarmMapSourceFile


def main() -> int:
    parser = argparse.ArgumentParser(description="Import FarmMap crop-region summary JSON into the backend DB.")
    parser.add_argument("--input", required=True, help="Summary JSON from build_farmmap_crop_region_summary.py")
    parser.add_argument("--replace-source", action="store_true", help="Delete existing rows for the same source_file before import.")
    args = parser.parse_args()
    return asyncio.run(import_main(Path(args.input), replace_source=args.replace_source))


async def import_main(path: Path, replace_source: bool) -> int:
    if not path.exists():
        print(f"Summary file not found: {path}", file=sys.stderr)
        return 2
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        print("Summary JSON must contain a rows array.", file=sys.stderr)
        return 2

    await init_db()
    saved = await import_summary(payload, replace_source=replace_source)
    print(json.dumps({"saved": saved, "source_file": payload.get("source_file")}, ensure_ascii=False, indent=2))
    return 0


async def import_summary(payload: dict[str, Any], replace_source: bool = False) -> int:
    rows = payload.get("rows") or []
    source_file = str(payload.get("source_file") or "unknown")
    source_year = payload.get("source_year")

    async with AsyncSessionLocal() as db:
        if replace_source:
            await db.execute(delete(FarmMapCropRegion).where(FarmMapCropRegion.source_file == source_file))
            await db.execute(delete(FarmMapSourceFile).where(FarmMapSourceFile.file_name == source_file))

        source = FarmMapSourceFile(
            file_name=source_file,
            file_format="summary_json",
            detected_crops_json=json.dumps(payload.get("item_counts") or {}, ensure_ascii=False),
            import_status="imported",
            notes=f"matched={payload.get('matched_source_rows', 0)}, unmatched={payload.get('unmatched_source_rows', 0)}",
        )
        db.add(source)

        objects = [
            FarmMapCropRegion(
                item_code=str(row.get("item_code") or ""),
                source_crop_name=_nullable(row.get("source_crop_name")),
                sido=str(row.get("sido") or ""),
                sigungu=_nullable(row.get("sigungu")),
                region_code=_nullable(row.get("region_code")),
                farm_count=_int_or_none(row.get("farm_count")),
                area_m2=_float_or_none(row.get("area_m2")),
                area_ha=_float_or_none(row.get("area_ha")),
                geometry_level=str(row.get("geometry_level") or "sigungu"),
                source_file=str(row.get("source_file") or source_file),
                source_year=_int_or_none(row.get("source_year", source_year)),
                source=str(row.get("source") or "farmmap"),
                confidence=str(row.get("confidence") or "source_checked"),
            )
            for row in rows
            if row.get("item_code") and row.get("sido")
        ]
        db.add_all(objects)
        await db.commit()
    return len(objects)


def _nullable(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
