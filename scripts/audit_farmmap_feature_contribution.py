from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.farmmap_capacity_features import FARMMAP_FEATURE_COLUMNS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit whether FarmMap training features are materially used by horizon models."
    )
    parser.add_argument("--features", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--horizons", default="1,7,14,30,90,180,365")
    parser.add_argument("--recent-rows", type=int, default=250)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    feature_path = Path(args.features)
    rows = _read_feature_rows(feature_path)
    recent_rows = rows[-args.recent_rows :] if args.recent_rows > 0 else rows
    models_dir = Path(args.models_dir)
    reports = []

    for horizon in _parse_horizons(args.horizons):
        model_path = models_dir / f"{args.model_prefix}_{horizon}d.json"
        if not model_path.exists():
            reports.append(
                {
                    "horizon_days": horizon,
                    "status": "missing_model",
                    "model_path": str(model_path),
                }
            )
            continue

        model = json.loads(model_path.read_text(encoding="utf-8"))
        reports.append(_horizon_report(horizon, model_path, model, recent_rows))

    payload = {
        "ok": True,
        "features": str(feature_path),
        "model_prefix": args.model_prefix,
        "recent_rows": len(recent_rows),
        "farmmap_feature_columns": FARMMAP_FEATURE_COLUMNS,
        "interpretation": {
            "mean_abs_contribution": "Average absolute linear contribution on recent feature rows.",
            "max_abs_contribution": "Largest absolute contribution observed on recent feature rows.",
            "rank_by_mean_abs": "Feature rank among all model features by recent mean absolute contribution; 1 is strongest.",
            "model_decision_note": "A feature can be useful even with small contribution, but large unstable contribution is a promotion risk.",
        },
        "horizons": reports,
        "summary": _summary(reports),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "horizons": len(reports)}, ensure_ascii=False, indent=2))
    return 0


def _horizon_report(horizon: int, model_path: Path, model: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    coefficients = model.get("coefficients") if isinstance(model.get("coefficients"), dict) else {}
    stats = model.get("feature_stats") if isinstance(model.get("feature_stats"), dict) else {}
    model_features = [str(feature) for feature in model.get("features", [])]
    contribution_stats = _contribution_stats(rows, model_features, coefficients, stats)
    farmmap_rows = []
    for feature in FARMMAP_FEATURE_COLUMNS:
        row = contribution_stats.get(feature) or _empty_feature_report(feature)
        row["coefficient"] = _round(_float(coefficients.get(feature)))
        row["is_in_model"] = feature in model_features
        farmmap_rows.append(row)

    used = [row for row in farmmap_rows if row["is_in_model"]]
    active = [row for row in used if row["mean_abs_contribution"] > 0]
    total_mean_abs = sum(row["mean_abs_contribution"] for row in contribution_stats.values())
    farmmap_mean_abs = sum(row["mean_abs_contribution"] for row in farmmap_rows)

    return {
        "horizon_days": horizon,
        "status": "audited",
        "model_path": str(model_path),
        "model_feature_count": len(model_features),
        "farmmap_features_in_model": len(used),
        "farmmap_features_active": len(active),
        "farmmap_mean_abs_contribution_share": _round(farmmap_mean_abs / total_mean_abs if total_mean_abs else 0.0),
        "top_farmmap_features": sorted(
            farmmap_rows,
            key=lambda row: (row["mean_abs_contribution"], row["max_abs_contribution"]),
            reverse=True,
        ),
        "top_overall_features": sorted(
            contribution_stats.values(),
            key=lambda row: row["mean_abs_contribution"],
            reverse=True,
        )[:12],
    }


def _contribution_stats(
    rows: list[dict[str, str]],
    features: list[str],
    coefficients: dict[str, Any],
    stats: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    raw: dict[str, list[float]] = {feature: [] for feature in features}
    for row in rows:
        for feature in features:
            coefficient = _float(coefficients.get(feature))
            feature_stats = stats.get(feature) if isinstance(stats.get(feature), dict) else {}
            z_score = _standardize(
                _float(row.get(feature)),
                _float(feature_stats.get("mean")),
                _float(feature_stats.get("std"), default=1.0),
            )
            raw[feature].append(coefficient * z_score)

    reports = {}
    mean_abs_pairs = []
    for feature, values in raw.items():
        abs_values = [abs(value) for value in values]
        mean_abs = mean(abs_values) if abs_values else 0.0
        mean_abs_pairs.append((feature, mean_abs))
        reports[feature] = {
            "feature": feature,
            "coefficient": _round(_float(coefficients.get(feature))),
            "mean_contribution": _round(mean(values) if values else 0.0),
            "mean_abs_contribution": _round(mean_abs),
            "max_abs_contribution": _round(max(abs_values) if abs_values else 0.0),
        }

    ranks = {
        feature: rank
        for rank, (feature, _value) in enumerate(
            sorted(mean_abs_pairs, key=lambda pair: pair[1], reverse=True),
            start=1,
        )
    }
    for feature, report in reports.items():
        report["rank_by_mean_abs"] = ranks.get(feature)
    return reports


def _read_feature_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    audited = [row for row in reports if row.get("status") == "audited"]
    if not audited:
        return {"audited_horizon_count": 0}
    return {
        "audited_horizon_count": len(audited),
        "mean_farmmap_contribution_share": _round(
            mean(float(row.get("farmmap_mean_abs_contribution_share") or 0.0) for row in audited)
        ),
        "horizons_with_active_farmmap": [
            row["horizon_days"] for row in audited if int(row.get("farmmap_features_active") or 0) > 0
        ],
        "horizons_without_active_farmmap": [
            row["horizon_days"] for row in audited if int(row.get("farmmap_features_active") or 0) <= 0
        ],
    }


def _empty_feature_report(feature: str) -> dict[str, Any]:
    return {
        "feature": feature,
        "coefficient": 0.0,
        "mean_contribution": 0.0,
        "mean_abs_contribution": 0.0,
        "max_abs_contribution": 0.0,
        "rank_by_mean_abs": None,
    }


def _parse_horizons(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _standardize(value: float, center: float, scale: float) -> float:
    if not scale:
        return 0.0
    return (value - center) / scale


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value: float) -> float:
    return round(float(value), 8)


if __name__ == "__main__":
    raise SystemExit(main())
