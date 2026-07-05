from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ALIASES_PATH = REPO_ROOT / "config" / "farmmap_crop_aliases.json"

CROP_FIELD_HINTS = ("crop", "crp", "작물", "품목", "재배", "농작물", "cult")
AREA_FIELD_HINTS = ("area", "면적", "m2", "㎡", "ha", "hect", "평")
REGION_FIELD_HINTS = ("sido", "시도", "sigungu", "시군구", "법정", "pnu", "region", "adm")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a downloaded FarmMap spatial source file before importing it.")
    parser.add_argument("--input", required=True, help="Path to FarmMap ZIP, CSV, GeoJSON, or JSON file.")
    parser.add_argument("--output", help="Optional JSON report path. Defaults to stdout only.")
    parser.add_argument("--sample-rows", type=int, default=500, help="Maximum rows/features to sample.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    aliases = load_aliases()
    report = audit_file(input_path, aliases, sample_rows=max(1, args.sample_rows))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    return 0 if report.get("import_readiness") != "blocked" else 1


def load_aliases() -> dict[str, list[str]]:
    raw = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    return {
        item_code: [str(alias).strip() for alias in payload.get("aliases", []) if str(alias).strip()]
        for item_code, payload in raw.items()
    }


def audit_file(path: Path, aliases: dict[str, list[str]], sample_rows: int) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return audit_zip(path, aliases, sample_rows)
    if suffix in {".csv", ".txt"}:
        rows, fields = read_csv_rows(path, sample_rows)
        return build_report(path, "csv", fields, rows, aliases, extra={})
    if suffix in {".geojson", ".json"}:
        rows, fields, extra = read_geojson_rows(path, sample_rows)
        return build_report(path, suffix.lstrip("."), fields, rows, aliases, extra=extra)
    if suffix == ".dbf":
        rows, fields, extra = read_dbf_rows(path, sample_rows)
        return build_report(path, "dbf", fields, rows, aliases, extra=extra)
    if suffix == ".shp":
        return build_report(
            path,
            "shp",
            [],
            [],
            aliases,
            extra={"note": "SHP parsing needs a DBF reader such as pyshp or GDAL. Prefer auditing the original ZIP or converted CSV/GeoJSON."},
            blocked_reason="shp_reader_not_available",
        )
    return build_report(path, suffix.lstrip(".") or "unknown", [], [], aliases, extra={}, blocked_reason="unsupported_format")


def audit_zip(path: Path, aliases: dict[str, list[str]], sample_rows: int) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        lower = [name.lower() for name in names]
        csv_names = [name for name in names if name.lower().endswith((".csv", ".txt"))]
        geojson_names = [name for name in names if name.lower().endswith((".geojson", ".json"))]
        shp_names = [name for name in names if name.lower().endswith(".shp")]
        dbf_names = [name for name in names if name.lower().endswith(".dbf")]

        if csv_names:
            with zf.open(csv_names[0]) as fp:
                rows, fields = read_csv_stream(fp, sample_rows)
            return build_report(
                path,
                "zip/csv",
                fields,
                rows,
                aliases,
                extra={"entries": names[:50], "sample_entry": csv_names[0], "entry_count": len(names)},
            )
        if geojson_names:
            with zf.open(geojson_names[0]) as fp:
                data = json.loads(fp.read().decode("utf-8-sig"))
            rows, fields, extra = rows_from_geojson(data, sample_rows)
            extra.update({"entries": names[:50], "sample_entry": geojson_names[0], "entry_count": len(names)})
            return build_report(path, "zip/geojson", fields, rows, aliases, extra=extra)
        if dbf_names:
            with zf.open(dbf_names[0]) as fp:
                rows, fields, extra = read_dbf_stream(fp.read(), sample_rows)
            extra.update({
                "entries": names[:50],
                "sample_entry": dbf_names[0],
                "entry_count": len(names),
                "shp_count": len(shp_names),
                "dbf_count": len(dbf_names),
            })
            return build_report(path, "zip/dbf", fields, rows, aliases, extra=extra)
        if shp_names:
            return build_report(
                path,
                "zip/shp",
                [],
                [],
                aliases,
                extra={
                    "entries": names[:50],
                    "entry_count": len(names),
                    "shp_count": len(shp_names),
                    "dbf_count": len(dbf_names),
                    "note": "ZIP contains SHP/DBF. Install pyshp or GDAL, or convert to GeoJSON/CSV for import.",
                },
                blocked_reason="shp_reader_not_available",
            )
        return build_report(
            path,
            "zip",
            [],
            [],
            aliases,
            extra={"entries": names[:50], "entry_count": len(names), "lowercase_entries": lower[:10]},
            blocked_reason="no_supported_table_entry",
        )


def read_csv_rows(path: Path, sample_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return read_csv_stream(fp, sample_rows)


def read_csv_stream(fp: Any, sample_rows: int) -> tuple[list[dict[str, Any]], list[str]]:
    text = fp.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    sample = text.splitlines()
    dialect = csv.Sniffer().sniff("\n".join(sample[:10])) if sample else csv.excel
    reader = csv.DictReader(sample, dialect=dialect)
    rows = []
    for idx, row in enumerate(reader):
        if idx >= sample_rows:
            break
        rows.append(dict(row))
    return rows, list(reader.fieldnames or [])


def read_geojson_rows(path: Path, sample_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return rows_from_geojson(data, sample_rows)


def read_dbf_rows(path: Path, sample_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    return read_dbf_stream(path.read_bytes(), sample_rows)


def read_dbf_stream(raw: bytes, sample_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    if len(raw) < 33:
        return [], [], {"note": "DBF file is too small."}

    record_count = struct.unpack("<I", raw[4:8])[0]
    header_len = struct.unpack("<H", raw[8:10])[0]
    record_len = struct.unpack("<H", raw[10:12])[0]
    fields = []
    pos = 32
    while pos + 32 <= len(raw) and raw[pos] != 0x0D:
        desc = raw[pos:pos + 32]
        name = decode_dbf_text(desc[:11]).split("\x00", 1)[0].strip()
        field_type = chr(desc[11])
        length = desc[16]
        decimal_count = desc[17]
        if name:
            fields.append({
                "name": name,
                "type": field_type,
                "length": length,
                "decimal_count": decimal_count,
            })
        pos += 32

    rows = []
    max_rows = min(record_count, sample_rows)
    for idx in range(max_rows):
        start = header_len + idx * record_len
        end = start + record_len
        if end > len(raw):
            break
        record = raw[start:end]
        if not record or record[0:1] == b"*":
            continue
        offset = 1
        row: dict[str, Any] = {}
        for field in fields:
            length = int(field["length"])
            chunk = record[offset:offset + length]
            offset += length
            row[str(field["name"])] = decode_dbf_value(chunk, str(field["type"]))
        rows.append(row)

    return rows, [str(field["name"]) for field in fields], {
        "dbf_record_count": record_count,
        "dbf_sample_count": len(rows),
        "dbf_header_length": header_len,
        "dbf_record_length": record_len,
        "dbf_fields": fields,
    }


def decode_dbf_value(raw: bytes, field_type: str) -> Any:
    text = decode_dbf_text(raw).strip()
    if not text:
        return ""
    if field_type in {"N", "F", "B"}:
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return text
    if field_type == "L":
        return text.upper() in {"Y", "T", "1"}
    return text


def decode_dbf_text(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr", "latin1"):
        try:
            return raw.decode(encoding).rstrip("\x00")
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace").rstrip("\x00")


def rows_from_geojson(data: dict[str, Any], sample_rows: int) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        return [], [], {"feature_count": 0, "note": "JSON is not a GeoJSON FeatureCollection."}
    rows = []
    fields: set[str] = set()
    for feature in features[:sample_rows]:
        props = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(props, dict):
            continue
        rows.append(props)
        fields.update(str(key) for key in props.keys())
    return rows, sorted(fields), {"feature_count": len(features)}


def build_report(
    path: Path,
    file_format: str,
    fields: list[str],
    rows: list[dict[str, Any]],
    aliases: dict[str, list[str]],
    extra: dict[str, Any],
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    crop_fields = matching_fields(fields, CROP_FIELD_HINTS)
    area_fields = matching_fields(fields, AREA_FIELD_HINTS)
    region_fields = matching_fields(fields, REGION_FIELD_HINTS)
    crop_values = collect_values(rows, crop_fields)
    alias_hits = match_aliases(crop_values, aliases)

    readiness = "ready_for_mapping"
    issues = []
    if blocked_reason:
        readiness = "blocked"
        issues.append(blocked_reason)
    if not crop_fields:
        readiness = "needs_field_mapping" if readiness != "blocked" else readiness
        issues.append("crop_field_not_detected")
    if not area_fields:
        issues.append("area_field_not_detected")
    if not region_fields:
        issues.append("region_field_not_detected")
    if crop_fields and not alias_hits:
        readiness = "needs_alias_review" if readiness != "blocked" else readiness
        issues.append("no_alias_hits_for_current_items")

    return {
        "file": str(path),
        "format": file_format,
        "fields": fields,
        "row_sample_count": len(rows),
        "detected": {
            "crop_fields": crop_fields,
            "area_fields": area_fields,
            "region_fields": region_fields,
            "crop_values_top": crop_values.most_common(30),
            "alias_hits": alias_hits,
        },
        "import_readiness": readiness,
        "issues": issues,
        "extra": extra,
    }


def matching_fields(fields: list[str], hints: tuple[str, ...]) -> list[str]:
    result = []
    for field in fields:
        folded = field.lower()
        if any(hint.lower() in folded for hint in hints):
            result.append(field)
    return result


def collect_values(rows: list[dict[str, Any]], fields: list[str]) -> Counter[str]:
    values: Counter[str] = Counter()
    for row in rows:
        for field in fields:
            value = str(row.get(field) or "").strip()
            if value:
                values[value] += 1
    return values


def match_aliases(values: Counter[str], aliases: dict[str, list[str]]) -> dict[str, dict[str, int]]:
    hits: dict[str, dict[str, int]] = {}
    for raw_value, count in values.items():
        compact = raw_value.replace(" ", "")
        for item_code, item_aliases in aliases.items():
            for alias in item_aliases:
                if alias.replace(" ", "") and alias.replace(" ", "") in compact:
                    hits.setdefault(item_code, {})[raw_value] = count
                    break
    return hits


if __name__ == "__main__":
    raise SystemExit(main())
