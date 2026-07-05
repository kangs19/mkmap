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
from app.models.farmmap import FarmMapLanduseRegion, FarmMapSourceFile


def main() -> int:
    parser = argparse.ArgumentParser(description="Import FarmMap land-use region summary JSON into the backend DB.")
    parser.add_argument("--input", required=True, help="Summary JSON from build_farmmap_landuse_region_summary.py")
    parser.add_argument("--replace-source", action="store_true", help="Delete existing rows for the same source_file before import.")
    args = parser.parse_args()
    return asyncio.run(import_main(resolve_input_path(args.input), replace_source=args.replace_source))


def resolve_input_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


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

    async with AsyncSessionLocal() as db:
        if replace_source:
            await db.execute(delete(FarmMapLanduseRegion).where(FarmMapLanduseRegion.source_file == source_file))
            await db.execute(delete(FarmMapSourceFile).where(FarmMapSourceFile.file_name == source_file))

        source = FarmMapSourceFile(
            file_name=source_file,
            file_format="landuse_summary_json",
            detected_fields_json=json.dumps(["sido", "sigungu", "landuse_class", "parcel_count", "area_m2", "area_ha"], ensure_ascii=False),
            detected_crops_json=json.dumps({}, ensure_ascii=False),
            import_status="imported_landuse_only",
            notes=f"source_rows={payload.get('source_rows', 0)}, total_area_ha={payload.get('total_area_ha')}",
        )
        db.add(source)

        objects = [
            FarmMapLanduseRegion(
                sido=str(row.get("sido") or ""),
                sigungu=_nullable(row.get("sigungu")),
                landuse_class=str(row.get("landuse_class") or "unknown"),
                parcel_count=_int_or_none(row.get("parcel_count")),
                area_m2=_float_or_none(row.get("area_m2")),
                area_ha=_float_or_none(row.get("area_ha")),
                source_file=str(row.get("source_file") or source_file),
                source=str(row.get("source") or "farmmap"),
                confidence="landuse_only",
            )
            for row in rows
            if row.get("sido") and row.get("landuse_class")
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
