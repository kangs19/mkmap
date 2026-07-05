from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_MODULE_PATH = REPO_ROOT / "scripts" / "train_price_baseline_model.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit overfit and temporal robustness for horizon price models.")
    parser.add_argument("--features", required=True)
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--horizons", default="1,7,14,30,90,180,365")
    parser.add_argument("--min-train-rows", type=int, default=120)
    parser.add_argument("--samples-per-era", type=int, default=5)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    train_module = _load_train_module()
    horizons = [int(part.strip()) for part in args.horizons.split(",") if part.strip()]
    models_dir = Path(args.models_dir)

    horizon_reports = []
    for horizon in horizons:
        target_column = f"target_{horizon}d_change"
        model_path = models_dir / f"{args.model_prefix}_{horizon}d.json"
        backtest_path = models_dir / f"{args.model_prefix}_{horizon}d_backtest.json"
        evaluation_path = models_dir / f"{args.model_prefix}_{horizon}d_evaluation.json"
        if not model_path.exists():
            continue
        rows, features = train_module._read_rows(Path(args.features), target_column)
        model = json.loads(model_path.read_text(encoding="utf-8"))
        evaluation = _read_json(evaluation_path)
        recent_backtest = _read_json(backtest_path)
        train_rows, test_rows = train_module._time_split(rows)
        threshold = float(model.get("direction_threshold") or 0.015)
        train_metrics = train_module._evaluate(model, train_rows, threshold)
        test_metrics = model.get("metrics", {})
        temporal_backtest = _temporal_backtest(
            train_module=train_module,
            rows=rows,
            features=features,
            min_train_rows=args.min_train_rows,
            samples_per_era=args.samples_per_era,
        )
        horizon_reports.append(
            _horizon_report(
                horizon=horizon,
                model=model,
                evaluation=evaluation,
                recent_backtest=recent_backtest,
                train_metrics=train_metrics,
                test_metrics=test_metrics,
                temporal_backtest=temporal_backtest,
            )
        )

    payload = {
        "ok": True,
        "model_prefix": args.model_prefix,
        "features": str(Path(args.features)),
        "interpretation": {
            "overfit_risk": "Compares train vs holdout and rolling backtest. Large train-test gaps or weak early/mid eras are risk signals.",
            "temporal_backtest": "Each sampled date is predicted by a model trained only on rows before that date.",
        },
        "horizons": horizon_reports,
        "summary": _summary(horizon_reports),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "horizons": len(horizon_reports)}, ensure_ascii=False, indent=2))
    return 0


def _load_train_module() -> Any:
    spec = importlib.util.spec_from_file_location("train_price_baseline_model", TRAIN_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {TRAIN_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _temporal_backtest(
    *,
    train_module: Any,
    rows: list[dict[str, float | str]],
    features: list[str],
    min_train_rows: int,
    samples_per_era: int,
) -> dict[str, Any]:
    dates = sorted({str(row["base_date"]) for row in rows})
    eligible = []
    for test_date in dates[1:]:
        train_rows = [row for row in rows if str(row["base_date"]) < test_date]
        test_rows = [row for row in rows if str(row["base_date"]) == test_date]
        if len(train_rows) >= min_train_rows and test_rows:
            eligible.append((test_date, train_rows, test_rows))
    if not eligible:
        return {"window_count": 0, "eras": {}}

    era_windows = _sample_eras(eligible, samples_per_era)
    era_reports = {}
    for era, windows in era_windows.items():
        predictions = []
        window_reports = []
        for test_date, train_rows, test_rows in windows:
            usable_features = [
                feature
                for feature in features
                if any(abs(float(row[feature])) > 0 for row in train_rows)
            ]
            if len(train_rows) < 10 or not usable_features:
                continue
            inner_train, validation = train_module._time_split(train_rows)
            threshold = 0.015
            if len(inner_train) >= 10 and validation:
                threshold = train_module._tune_direction_threshold(
                    train_module._fit_linear_model(inner_train, usable_features),
                    validation,
                )
            window_model = train_module._fit_linear_model(train_rows, usable_features)
            window_predictions = train_module._prediction_rows(window_model, test_rows, threshold)
            predictions.extend(window_predictions)
            window_reports.append(
                {
                    "test_date": test_date,
                    "train_rows": len(train_rows),
                    "test_rows": len(test_rows),
                    "feature_count": len(usable_features),
                    "metrics": train_module._aggregate_prediction_metrics(window_predictions),
                }
            )
        era_reports[era] = {
            "window_count": len(window_reports),
            "prediction_count": len(predictions),
            "metrics": train_module._aggregate_prediction_metrics(predictions),
            "windows": window_reports,
        }

    return {
        "eligible_window_count": len(eligible),
        "sampled_window_count": sum(era["window_count"] for era in era_reports.values()),
        "eras": era_reports,
    }


def _sample_eras(windows: list[Any], samples_per_era: int) -> dict[str, list[Any]]:
    count = len(windows)
    early = windows[:samples_per_era]
    midpoint = count // 2
    half = samples_per_era // 2
    middle_start = max(0, midpoint - half)
    middle = windows[middle_start : middle_start + samples_per_era]
    recent = windows[-samples_per_era:]
    return {"early": early, "middle": middle, "recent": recent}


def _horizon_report(
    *,
    horizon: int,
    model: dict[str, Any],
    evaluation: dict[str, Any],
    recent_backtest: dict[str, Any],
    train_metrics: dict[str, float],
    test_metrics: dict[str, Any],
    temporal_backtest: dict[str, Any],
) -> dict[str, Any]:
    test_direction = _float(test_metrics.get("direction_accuracy"))
    train_direction = _float(train_metrics.get("direction_accuracy"))
    test_mae = _float(test_metrics.get("mae"))
    train_mae = max(_float(train_metrics.get("mae")), 0.000001)
    recent_summary = recent_backtest.get("summary", {}) if isinstance(recent_backtest.get("summary"), dict) else {}
    era_metrics = temporal_backtest.get("eras", {})
    risk_reasons = []
    if train_direction - test_direction > 0.15:
        risk_reasons.append("train_direction_much_higher_than_test")
    if test_mae / train_mae > 1.75:
        risk_reasons.append("test_mae_much_higher_than_train")
    for era_name, era in era_metrics.items():
        metrics = era.get("metrics", {}) if isinstance(era, dict) else {}
        if _float(metrics.get("direction_accuracy")) < 0.6:
            risk_reasons.append(f"{era_name}_temporal_direction_below_0.60")
    item_model_count = int(evaluation.get("item_model_count") or len(model.get("item_models", {})))
    return {
        "horizon_days": horizon,
        "train_rows": model.get("train_rows"),
        "test_rows": model.get("test_rows"),
        "feature_count": len(model.get("features", [])),
        "item_model_count": item_model_count,
        "train_metrics": _round_metrics(train_metrics),
        "test_metrics": _round_metrics(test_metrics),
        "recent_rolling_backtest": _round_metrics(recent_summary),
        "temporal_backtest": temporal_backtest,
        "overfit_gap": {
            "direction_train_minus_test": _round(train_direction - test_direction),
            "mae_test_div_train": _round(test_mae / train_mae),
        },
        "risk_level": _risk_level(risk_reasons),
        "risk_reasons": sorted(set(risk_reasons)),
    }


def _summary(horizon_reports: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "horizon_count": len(horizon_reports),
        "high_risk_horizons": [
            row["horizon_days"] for row in horizon_reports if row.get("risk_level") == "high"
        ],
        "medium_risk_horizons": [
            row["horizon_days"] for row in horizon_reports if row.get("risk_level") == "medium"
        ],
        "low_risk_horizons": [
            row["horizon_days"] for row in horizon_reports if row.get("risk_level") == "low"
        ],
    }


def _risk_level(reasons: list[str]) -> str:
    if any("below_0.60" in reason for reason in reasons):
        return "high"
    if reasons:
        return "medium"
    return "low"


def _round_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _round(value) if isinstance(value, (int, float)) else value
        for key, value in metrics.items()
        if key in {"mae", "rmse", "sign_accuracy", "direction_accuracy", "prediction_count", "window_count"}
    }


def _float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return number


def _round(value: Any) -> float:
    return round(_float(value), 6)


if __name__ == "__main__":
    raise SystemExit(main())
