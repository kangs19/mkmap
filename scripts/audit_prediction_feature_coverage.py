from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.registry import default_registry

FEATURE_GROUPS = {
    "price_target": ["kamis_price", "agromarket_retail_price"],
    "price_market": [
        "agromarket_wholesale_price",
        "agromarket_retail_price",
        "agromarket_settlement",
        "agromarket_auction_price",
        "at_regional_price",
        "at_market_settlement",
    ],
    "agri_weather": ["kma_crop_weather", "rda_agri_weather"],
    "disaster_event": ["weather_alert", "impact_forecast", "typhoon", "rain_reservoir", "weather_alert_insurance"],
    "forecast_context": ["midterm_forecast", "satellite", "weather_chart"],
    "production_region": ["kosis_production"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit cached feature coverage for prediction engines.")
    parser.add_argument("--start", default="2024-08-01")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--items", nargs="*", default=None, help="Defaults to all metadata registry items.")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    item_codes = args.items or sorted(default_registry().all_items())
    features_root = REPO_ROOT / "data" / "features"
    diagnostics_root = REPO_ROOT / "data" / "diagnostics"

    payload = {
        "ok": True,
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "items": item_codes,
        "cache_root": str(features_root),
        "groups": {},
        "engine_readiness": {},
        "notes": [],
        "diagnostic_files": _diagnostic_files(diagnostics_root),
    }

    for group_name, prefixes in FEATURE_GROUPS.items():
        group = _audit_group(features_root, start, end, item_codes, prefixes)
        payload["groups"][group_name] = group
        payload["engine_readiness"][group_name] = _readiness(group_name, group)

    payload["notes"] = _notes(payload["groups"])
    out_path = Path(args.output) if args.output else diagnostics_root / "prediction_feature_coverage.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "output": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


def _audit_group(
    root: Path,
    start: date,
    end: date,
    items: list[str],
    prefixes: list[str],
) -> dict[str, Any]:
    by_prefix: dict[str, Any] = {}
    group_dates: set[date] = set()
    group_items: dict[str, set[date]] = {item: set() for item in items}

    for prefix in prefixes:
        result = _audit_prefix(root, start, end, items, prefix)
        by_prefix[prefix] = result
        for raw_day in result["dates"]:
            group_dates.add(date.fromisoformat(raw_day))
        for item, item_result in result["by_item"].items():
            for raw_day in item_result["dates"]:
                group_items.setdefault(item, set()).add(date.fromisoformat(raw_day))

    return {
        "prefixes": by_prefix,
        "unique_date_count": len(group_dates),
        "date_min": min(group_dates).isoformat() if group_dates else None,
        "date_max": max(group_dates).isoformat() if group_dates else None,
        "by_item": {
            item: {
                "unique_date_count": len(days),
                "date_min": min(days).isoformat() if days else None,
                "date_max": max(days).isoformat() if days else None,
            }
            for item, days in sorted(group_items.items())
        },
    }


def _audit_prefix(root: Path, start: date, end: date, items: list[str], prefix: str) -> dict[str, Any]:
    dates: set[date] = set()
    by_item: dict[str, set[date]] = {item: set() for item in items}
    file_count = 0
    row_count = 0

    for dated_dir in sorted(root.glob("*")):
        if not dated_dir.is_dir():
            continue
        try:
            folder_date = datetime.strptime(dated_dir.name, "%Y%m%d").date()
        except ValueError:
            continue
        if folder_date < start or folder_date > end:
            continue
        for path in dated_dir.glob(f"{prefix}*.json"):
            rows = _read_rows(path)
            if rows is None:
                continue
            file_count += 1
            row_count += len(rows)
            if not rows:
                continue
            row_dates = _row_dates(rows, fallback=folder_date)
            dates.update(day for day in row_dates if start <= day <= end)
            matched_item = _item_from_name(path.stem, prefix, items)
            if matched_item:
                by_item[matched_item].update(day for day in row_dates if start <= day <= end)
            else:
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    item = str(row.get("item_code") or "")
                    row_date = _parse_row_date(row, fallback=folder_date)
                    if item in by_item and start <= row_date <= end:
                        by_item[item].add(row_date)

    return {
        "file_count": file_count,
        "row_count": row_count,
        "unique_date_count": len(dates),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "dates": [day.isoformat() for day in sorted(dates)],
        "by_item": {
            item: {
                "unique_date_count": len(days),
                "date_min": min(days).isoformat() if days else None,
                "date_max": max(days).isoformat() if days else None,
                "dates": [day.isoformat() for day in sorted(days)],
            }
            for item, days in sorted(by_item.items())
        },
    }


def _read_rows(path: Path) -> list[Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "features", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return [payload] if payload else []
    return []


def _row_dates(rows: list[Any], fallback: date) -> set[date]:
    dates = set()
    for row in rows:
        if isinstance(row, dict):
            dates.add(_parse_row_date(row, fallback=fallback))
    return dates or {fallback}


def _parse_row_date(row: dict[str, Any], fallback: date) -> date:
    raw = row.get("base_date") or row.get("date") or row.get("ymd") or row.get("target_date")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            pass
        try:
            return datetime.strptime(str(raw)[:8], "%Y%m%d").date()
        except ValueError:
            pass
    return fallback


def _item_from_name(stem: str, prefix: str, items: list[str]) -> str | None:
    suffix = stem.removeprefix(prefix).strip("_")
    for item in sorted(items, key=len, reverse=True):
        if suffix == item or suffix.endswith("_" + item):
            return item
    return None


def _readiness(group_name: str, group: dict[str, Any]) -> dict[str, Any]:
    date_count = int(group["unique_date_count"])
    by_item_counts = [int(row["unique_date_count"]) for row in group["by_item"].values()]
    min_item_count = min(by_item_counts) if by_item_counts else 0
    if group_name in {"price_target", "price_market"}:
        status = "usable" if min_item_count >= 180 else "insufficient"
    elif group_name == "agri_weather":
        status = "usable_if_backfilled" if date_count >= 30 else "needs_backfill_or_mapping"
    elif group_name == "production_region":
        status = "usable_static_annual" if date_count >= 1 else "needs_collection"
    else:
        status = "context_only_or_recent" if date_count >= 1 else "needs_collection"
    return {"status": status, "unique_date_count": date_count, "min_item_date_count": min_item_count}


def _diagnostic_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    return [str(path.relative_to(REPO_ROOT)) for path in sorted(root.rglob("*.json"))]


def _notes(groups: dict[str, Any]) -> list[str]:
    notes = []
    if groups["agri_weather"]["unique_date_count"] < groups["price_market"]["unique_date_count"]:
        notes.append("Weather cache coverage is much thinner than market-price coverage; yearly models need weather backfill or an explicit missing-feature strategy.")
    if groups["production_region"]["unique_date_count"] < 1:
        notes.append("KOSIS/FarmMap production-region features are not present in local cache for this range.")
    notes.append("Forecast-context services such as midterm, satellite, weather chart are recent/contextual and are not expected to provide multi-year supervised history.")
    return notes


if __name__ == "__main__":
    raise SystemExit(main())
