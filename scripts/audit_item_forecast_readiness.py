from __future__ import annotations

import argparse
import csv
import json
import sys
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
    parser = argparse.ArgumentParser(description="Audit item-level forecast readiness before public promotion.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--start", default="2025-07-06")
    parser.add_argument("--end", default=None, help="Defaults to --date.")
    parser.add_argument("--items", nargs="*", default=None, help="Defaults to all metadata registry items.")
    parser.add_argument("--features-root", default=str(REPO_ROOT / "data" / "features"))
    parser.add_argument("--training-table", default=None)
    parser.add_argument("--models-dir", default=str(REPO_ROOT / "data" / "model" / "horizons"))
    parser.add_argument("--model-prefix", default=None)
    parser.add_argument("--horizons", default="1,14,30,90,180")
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-ready-score", type=int, default=75)
    parser.add_argument("--min-watch-score", type=int, default=55)
    parser.add_argument("--min-backtest-direction", type=float, default=0.60)
    parser.add_argument("--min-backtest-predictions", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end or args.date)
    item_codes = args.items or sorted(default_registry().all_items())
    training_table = Path(args.training_table) if args.training_table else REPO_ROOT / "data" / "model" / f"price_training_table_{target_date:%Y%m%d}.csv"
    model_prefix = args.model_prefix or _latest_model_prefix(Path(args.models_dir))
    horizons = _parse_horizons(args.horizons)

    metadata = default_registry().all_items()
    feature_coverage = _feature_coverage(Path(args.features_root), start, end, item_codes)
    target_rows = _training_target_rows(training_table, horizons)
    backtests = _load_backtests(Path(args.models_dir), model_prefix, horizons) if model_prefix else {}

    items = []
    for item_code in item_codes:
        item = metadata[item_code]
        item_report = _item_report(
            item_code=item_code,
            item=item,
            horizons=horizons,
            target_rows=target_rows.get(item_code, {}),
            feature_coverage=feature_coverage.get(item_code, {}),
            backtests=backtests,
            args=args,
        )
        items.append(item_report)

    payload = {
        "ok": True,
        "date": target_date.isoformat(),
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "training_table": str(training_table),
        "model_prefix": model_prefix,
        "thresholds": {
            "min_ready_score": args.min_ready_score,
            "min_watch_score": args.min_watch_score,
            "min_backtest_direction": args.min_backtest_direction,
            "min_backtest_predictions": args.min_backtest_predictions,
        },
        "summary": _summary(items),
        "items": items,
    }
    output = Path(args.output) if args.output else REPO_ROOT / "data" / "diagnostics" / f"item_forecast_readiness_{target_date:%Y%m%d}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def _item_report(
    *,
    item_code: str,
    item: dict[str, Any],
    horizons: list[int],
    target_rows: dict[int, int],
    feature_coverage: dict[str, int],
    backtests: dict[int, dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    score, reasons, strengths = _readiness_score(item, target_rows, feature_coverage)
    horizon_reports = []
    for horizon in horizons:
        metrics = backtests.get(horizon, {}).get(item_code, {})
        direction = _float(metrics.get("direction_accuracy"))
        prediction_count = int(metrics.get("prediction_count") or 0)
        horizon_reasons = []
        if target_rows.get(horizon, 0) < _target_row_floor(horizon):
            horizon_reasons.append("target_history_short")
        if prediction_count < args.min_backtest_predictions:
            horizon_reasons.append("backtest_sample_short")
        if direction is None:
            horizon_reasons.append("missing_backtest")
        elif direction < args.min_backtest_direction:
            horizon_reasons.append("low_backtest_direction")
        horizon_reports.append(
            {
                "horizon_days": horizon,
                "status": "candidate" if not horizon_reasons and score >= args.min_ready_score else "watch" if not horizon_reasons else "hold",
                "target_rows": target_rows.get(horizon, 0),
                "backtest_direction_accuracy": direction,
                "backtest_mae": _float(metrics.get("mae")),
                "backtest_prediction_count": prediction_count,
                "reasons": horizon_reasons,
            }
        )

    status = _overall_status(score, horizon_reports, args)
    return {
        "item_code": item_code,
        "item_name": item.get("item_name"),
        "status": status,
        "readiness_score": score,
        "reasons": reasons,
        "strengths": strengths,
        "source_flags": {
            "manual_review_required": bool(item.get("source_coverage", {}).get("manual_review_required")),
            "kamis": bool(item.get("source_coverage", {}).get("kamis")),
            "kosis": bool(item.get("source_coverage", {}).get("kosis")),
            "kma_crop_weather_status": item.get("external_mappings", {}).get("kma_crop_weather", {}).get("mapping_status"),
        },
        "feature_date_counts": feature_coverage,
        "horizons": horizon_reports,
        "public_recommendation": _recommendation(status),
    }


def _readiness_score(
    item: dict[str, Any],
    target_rows: dict[int, int],
    coverage: dict[str, int],
) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    strengths: list[str] = []

    max_target_rows = max(target_rows.values()) if target_rows else 0
    if max_target_rows >= 180:
        score += 25
        strengths.append("price_target_history_ready")
    elif max_target_rows >= 90:
        score += 15
        reasons.append("price_target_history_partial")
    else:
        reasons.append("price_target_history_short")

    market_days = int(coverage.get("price_market", 0))
    if market_days >= 180:
        score += 20
        strengths.append("regional_market_context_ready")
    elif market_days >= 60:
        score += 10
        reasons.append("regional_market_context_partial")
    else:
        reasons.append("regional_market_context_short")

    source_coverage = item.get("source_coverage", {})
    if bool(source_coverage.get("kosis")) or int(coverage.get("production_region", 0)) >= 1:
        score += 15
        strengths.append("production_region_mapping_ready")
    else:
        reasons.append("production_region_mapping_missing")

    weather_mapping = item.get("external_mappings", {}).get("kma_crop_weather", {})
    weather_status = str(weather_mapping.get("mapping_status") or "")
    weather_days = int(coverage.get("agri_weather", 0))
    if weather_status == "verified" and weather_days >= 30:
        score += 15
        strengths.append("agri_weather_mapping_ready")
    elif weather_status == "verified":
        score += 8
        reasons.append("agri_weather_cache_short")
    elif weather_days >= 30:
        score += 6
        reasons.append("agri_weather_mapping_not_verified")
    else:
        reasons.append("agri_weather_mapping_missing_or_short")

    event_days = int(coverage.get("disaster_event", 0))
    if event_days >= 30:
        score += 10
        strengths.append("disaster_event_context_present")
    elif event_days > 0:
        score += 5
        reasons.append("disaster_event_context_recent_only")
    else:
        reasons.append("disaster_event_context_missing")

    if not bool(source_coverage.get("manual_review_required")):
        score += 10
        strengths.append("metadata_review_complete")
    else:
        reasons.append("metadata_manual_review_required")

    if int(coverage.get("forecast_context", 0)) > 0:
        score += 5
        strengths.append("forecast_context_present")

    return min(score, 100), reasons, strengths


def _overall_status(items_score: int, horizons: list[dict[str, Any]], args: argparse.Namespace) -> str:
    candidate_horizons = [row for row in horizons if row["status"] == "candidate"]
    watch_horizons = [row for row in horizons if row["status"] == "watch"]
    if items_score >= args.min_ready_score and candidate_horizons:
        return "candidate"
    if items_score >= args.min_watch_score and (candidate_horizons or watch_horizons):
        return "watch"
    return "hold"


def _recommendation(status: str) -> str:
    if status == "candidate":
        return "Can be considered for public prediction after human review of item-level charts."
    if status == "watch":
        return "Keep visible only as experimental or low-confidence until missing feature sources improve."
    return "Do not expose as a trusted public forecast yet."


def _feature_coverage(root: Path, start: date, end: date, items: list[str]) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {item: {group: 0 for group in FEATURE_GROUPS} for item in items}
    for group, prefixes in FEATURE_GROUPS.items():
        item_dates = {item: set() for item in items}
        for prefix in prefixes:
            for item, days in _prefix_item_dates(root, start, end, items, prefix).items():
                item_dates[item].update(days)
        for item, days in item_dates.items():
            report[item][group] = len(days)
    return report


def _prefix_item_dates(root: Path, start: date, end: date, items: list[str], prefix: str) -> dict[str, set[date]]:
    by_item: dict[str, set[date]] = {item: set() for item in items}
    if not root.exists():
        return by_item
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
            matched_item = _item_from_name(path.stem, prefix, items)
            for row in rows:
                row_date = _parse_row_date(row, folder_date) if isinstance(row, dict) else folder_date
                if not (start <= row_date <= end):
                    continue
                row_item = str(row.get("item_code") or "") if isinstance(row, dict) else ""
                item = row_item if row_item in by_item else matched_item
                if item in by_item:
                    by_item[item].add(row_date)
    return by_item


def _training_target_rows(path: Path, horizons: list[int]) -> dict[str, dict[int, int]]:
    result: dict[str, dict[int, int]] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = str(row.get("item_code") or "")
            if not item:
                continue
            bucket = result.setdefault(item, {horizon: 0 for horizon in horizons})
            for horizon in horizons:
                raw = row.get(f"target_{horizon}d_change")
                if raw not in (None, ""):
                    bucket[horizon] += 1
    return result


def _load_backtests(models_dir: Path, model_prefix: str, horizons: list[int]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for horizon in horizons:
        path = models_dir / f"{model_prefix}_{horizon}d_backtest.json"
        if not path.exists():
            result[horizon] = {}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        by_item = summary.get("by_item") if isinstance(summary.get("by_item"), dict) else {}
        result[horizon] = by_item
    return result


def _latest_model_prefix(models_dir: Path) -> str | None:
    candidates = sorted(models_dir.glob("*_approval_report.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0].name.removesuffix("_approval_report.json")
    models = sorted(models_dir.glob("*_1d.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not models:
        return None
    return models[0].name.removesuffix("_1d.json")


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for item in items:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
    weakest = sorted(
        (
            {
                "item_code": item["item_code"],
                "status": item["status"],
                "readiness_score": item["readiness_score"],
                "reasons": item["reasons"][:5],
            }
            for item in items
        ),
        key=lambda row: (int(row["readiness_score"]), str(row["item_code"])),
    )[:10]
    return {
        "item_count": len(items),
        "by_status": dict(sorted(by_status.items())),
        "candidate_items": [item["item_code"] for item in items if item["status"] == "candidate"],
        "watch_items": [item["item_code"] for item in items if item["status"] == "watch"],
        "hold_items": [item["item_code"] for item in items if item["status"] == "hold"],
        "weakest_items": weakest,
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


def _target_row_floor(horizon: int) -> int:
    if horizon <= 14:
        return 180
    if horizon <= 90:
        return 120
    return 90


def _parse_horizons(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
