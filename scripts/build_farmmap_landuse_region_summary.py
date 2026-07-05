from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_farmmap_spatial_file import read_dbf_rows, read_zip_dbf_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build region-level FarmMap land-use summaries from DBF or SHP ZIP data.")
    parser.add_argument("--input", required=True, help="FarmMap DBF or ZIP containing DBF files.")
    parser.add_argument("--output", required=True, help="Output summary JSON path.")
    parser.add_argument("--class-field", default="CLSF_NM", help="FarmMap land-use class field.")
    parser.add_argument("--area-field", default="AREA", help="Area field in square meters.")
    parser.add_argument("--sido-field", default="__source_sido", help="Sido/province field.")
    parser.add_argument("--sigungu-field", default="__source_sigungu", help="Sigungu field.")
    parser.add_argument("--sample-rows", type=int, default=0, help="Limit rows for testing. 0 means all rows.")
    args = parser.parse_args()

    input_path = Path(args.input)
    rows, _fields = load_rows(input_path, args.sample_rows)
    summary = aggregate_landuse(
        rows=rows,
        class_field=args.class_field,
        area_field=args.area_field,
        sido_field=args.sido_field,
        sigungu_field=args.sigungu_field,
        source_file=input_path.name,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out_path),
        "row_count": len(summary["rows"]),
        "source_rows": summary["source_rows"],
        "total_area_ha": summary["total_area_ha"],
    }, ensure_ascii=False, indent=2))
    return 0


def load_rows(path: Path, sample_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    limit = sample_rows if sample_rows and sample_rows > 0 else 10_000_000
    if path.suffix.lower() == ".dbf":
        rows, fields, _extra = read_dbf_rows(path, limit)
        return rows, fields
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            dbf_names = [name for name in zf.namelist() if name.lower().endswith(".dbf")]
            if not dbf_names:
                raise ValueError("ZIP does not contain a DBF attribute table.")
            rows, fields, _extra = read_zip_dbf_rows(zf, dbf_names, limit)
            return rows, fields
    raise ValueError(f"Unsupported file type: {path.suffix}")


def aggregate_landuse(
    rows: list[dict[str, Any]],
    class_field: str,
    area_field: str,
    sido_field: str,
    sigungu_field: str,
    source_file: str,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_rows = 0
    for row in rows:
        sido = clean(row.get(sido_field)) or parse_addr(row.get("STDG_ADDR"))[0]
        sigungu = clean(row.get(sigungu_field)) or parse_addr(row.get("STDG_ADDR"))[1]
        landuse = clean(row.get(class_field)) or "unknown"
        area_m2 = parse_float(row.get(area_field)) or 0.0
        if not sido:
            continue
        key = (sido, sigungu, landuse)
        if key not in grouped:
            grouped[key] = {
                "sido": sido,
                "sigungu": sigungu or None,
                "landuse_class": landuse,
                "parcel_count": 0,
                "area_m2": 0.0,
                "area_ha": 0.0,
                "source": "farmmap",
                "source_file": source_file,
            }
        grouped[key]["parcel_count"] += 1
        grouped[key]["area_m2"] += area_m2
        grouped[key]["area_ha"] += area_m2 / 10_000.0
        source_rows += 1

    output_rows = []
    for row in grouped.values():
        row["area_m2"] = round(row["area_m2"], 4)
        row["area_ha"] = round(row["area_ha"], 6)
        output_rows.append(row)
    output_rows.sort(key=lambda r: (r["sido"], r.get("sigungu") or "", r["landuse_class"]))

    return {
        "source_file": source_file,
        "source_rows": source_rows,
        "total_area_ha": round(sum(row["area_ha"] for row in output_rows), 6),
        "rows": output_rows,
    }


def parse_addr(value: Any) -> tuple[str, str]:
    parts = clean(value).split()
    return (parts[0] if len(parts) >= 1 else "", parts[1] if len(parts) >= 2 else "")


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean(value: Any) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
