from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from audit_farmmap_spatial_file import (
    audit_file,
    load_aliases,
    read_csv_rows,
    read_dbf_rows,
    read_dbf_stream,
    read_geojson_rows,
)
import zipfile


def main() -> int:
    parser = argparse.ArgumentParser(description="Build item/region FarmMap summaries from audited CSV or GeoJSON data.")
    parser.add_argument("--input", required=True, help="CSV, GeoJSON, or JSON source file.")
    parser.add_argument("--output", required=True, help="Output summary JSON path.")
    parser.add_argument("--crop-field", help="Crop name field. Auto-detected when omitted.")
    parser.add_argument("--area-field", help="Area field in square meters by default. Auto-detected when omitted.")
    parser.add_argument("--area-unit", choices=["m2", "ha", "pyeong"], default="m2")
    parser.add_argument("--sido-field", help="Sido/province field. Auto-detected when omitted.")
    parser.add_argument("--sigungu-field", help="Sigungu field. Auto-detected when omitted.")
    parser.add_argument("--region-code-field", help="Optional region/PNU/admin code field.")
    parser.add_argument("--source-year", type=int)
    parser.add_argument("--sample-rows", type=int, default=0, help="Limit rows for dry-run sampling. 0 means all rows.")
    args = parser.parse_args()

    input_path = Path(args.input)
    aliases = load_aliases()
    audit = audit_file(input_path, aliases, sample_rows=1000)
    if audit.get("import_readiness") == "blocked":
        print(json.dumps(audit, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    rows, fields = load_rows(input_path, args.sample_rows)
    crop_field = args.crop_field or first(audit["detected"]["crop_fields"])
    area_field = args.area_field or first(audit["detected"]["area_fields"])
    sido_field = args.sido_field or first_field(fields, ["sido", "시도", "도"])
    sigungu_field = args.sigungu_field or first_field(fields, ["sigungu", "시군구", "군", "시"])
    region_code_field = args.region_code_field or first_field(fields, ["pnu", "법정", "adm", "code", "코드"])

    missing = [
        name
        for name, value in {
            "crop_field": crop_field,
            "sido_field": sido_field,
        }.items()
        if not value
    ]
    if missing:
        print(f"Missing required field mapping: {', '.join(missing)}", file=sys.stderr)
        print(json.dumps(audit, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    summary = aggregate_rows(
        rows=rows,
        aliases=aliases,
        crop_field=crop_field,
        area_field=area_field,
        area_unit=args.area_unit,
        sido_field=sido_field,
        sigungu_field=sigungu_field,
        region_code_field=region_code_field,
        source_file=input_path.name,
        source_year=args.source_year,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(out_path),
        "row_count": len(summary["rows"]),
        "matched_source_rows": summary["matched_source_rows"],
        "unmatched_source_rows": summary["unmatched_source_rows"],
        "item_counts": summary["item_counts"],
    }, ensure_ascii=False, indent=2))
    return 0


def load_rows(path: Path, sample_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    limit = sample_rows if sample_rows and sample_rows > 0 else 10_000_000
    if path.suffix.lower() in {".csv", ".txt"}:
        return read_csv_rows(path, limit)
    if path.suffix.lower() in {".geojson", ".json"}:
        rows, fields, _extra = read_geojson_rows(path, limit)
        return rows, fields
    if path.suffix.lower() == ".dbf":
        rows, fields, _extra = read_dbf_rows(path, limit)
        return rows, fields
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            dbf_names = [name for name in zf.namelist() if name.lower().endswith(".dbf")]
            if not dbf_names:
                raise ValueError("ZIP does not contain a DBF attribute table.")
            with zf.open(dbf_names[0]) as fp:
                rows, fields, _extra = read_dbf_stream(fp.read(), limit)
            return rows, fields
    raise ValueError(f"Unsupported file type: {path.suffix}")


def aggregate_rows(
    rows: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    crop_field: str,
    area_field: str | None,
    area_unit: str,
    sido_field: str,
    sigungu_field: str | None,
    region_code_field: str | None,
    source_file: str,
    source_year: int | None,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    matched = 0
    unmatched = 0
    item_counts: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        source_crop = clean(row.get(crop_field))
        item_code, confidence = match_item(source_crop, aliases)
        if not item_code:
            unmatched += 1
            continue
        sido = clean(row.get(sido_field))
        if not sido:
            unmatched += 1
            continue
        sigungu = clean(row.get(sigungu_field)) if sigungu_field else ""
        region_code = clean(row.get(region_code_field)) if region_code_field else ""
        key = (item_code, sido, sigungu, source_crop)
        if key not in grouped:
            grouped[key] = {
                "item_code": item_code,
                "source_crop_name": source_crop,
                "sido": sido,
                "sigungu": sigungu or None,
                "region_code": region_code or None,
                "farm_count": 0,
                "area_m2": 0.0,
                "area_ha": 0.0,
                "geometry_level": "sigungu" if sigungu else "sido",
                "source_file": source_file,
                "source_year": source_year,
                "source": "farmmap",
                "confidence": confidence,
            }
        area_m2 = parse_area(row.get(area_field), area_unit) if area_field else None
        grouped[key]["farm_count"] += 1
        if area_m2 is not None:
            grouped[key]["area_m2"] += area_m2
            grouped[key]["area_ha"] += area_m2 / 10_000.0
        matched += 1
        item_counts[item_code] += 1

    output_rows = []
    for row in grouped.values():
        row["area_m2"] = round(row["area_m2"], 4) if row["area_m2"] else None
        row["area_ha"] = round(row["area_ha"], 6) if row["area_ha"] else None
        output_rows.append(row)
    output_rows.sort(key=lambda r: (r["item_code"], r["sido"], r.get("sigungu") or "", r["source_crop_name"]))

    return {
        "source_file": source_file,
        "source_year": source_year,
        "matched_source_rows": matched,
        "unmatched_source_rows": unmatched,
        "item_counts": dict(sorted(item_counts.items())),
        "rows": output_rows,
    }


def match_item(source_crop: str, aliases: dict[str, list[str]]) -> tuple[str | None, str]:
    compact = source_crop.replace(" ", "")
    if not compact:
        return None, "missing_crop_name"
    for item_code, item_aliases in aliases.items():
        for alias in item_aliases:
            alias_compact = alias.replace(" ", "")
            if compact == alias_compact:
                return item_code, "exact_alias"
    for item_code, item_aliases in aliases.items():
        for alias in item_aliases:
            alias_compact = alias.replace(" ", "")
            if alias_compact and alias_compact in compact:
                return item_code, "partial_alias"
    return None, "unmatched"


def parse_area(value: Any, unit: str) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if unit == "ha":
        return number * 10_000.0
    if unit == "pyeong":
        return number * 3.305785
    return number


def clean(value: Any) -> str:
    return str(value or "").strip()


def first(values: list[str]) -> str | None:
    return values[0] if values else None


def first_field(fields: list[str], hints: list[str]) -> str | None:
    for hint in hints:
        for field in fields:
            if hint.lower() in field.lower():
                return field
    return None


if __name__ == "__main__":
    raise SystemExit(main())
