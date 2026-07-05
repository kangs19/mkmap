from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_MODULE_PATH = REPO_ROOT / "scripts" / "train_price_baseline_model.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Break temporal horizon weakness down by item and era.")
    parser.add_argument("--features", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--horizons", default="1,14,30,180")
    parser.add_argument("--min-train-rows", type=int, default=120)
    parser.add_argument("--samples-per-era", type=int, default=5)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    train_module = _load_train_module()
    reports = []
    for horizon in _parse_horizons(args.horizons):
        target_column = f"target_{horizon}d_change"
        rows, features = train_module._read_rows(Path(args.features), target_column)
        reports.append(
            _horizon_breakdown(
                train_module=train_module,
                horizon=horizon,
                rows=rows,
                features=features,
                min_train_rows=args.min_train_rows,
                samples_per_era=args.samples_per_era,
            )
        )

    payload = {
        "ok": True,
        "model_prefix": args.model_prefix,
        "features": str(Path(args.features)),
        "horizons": reports,
        "summary": _summary(reports),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "horizons": len(reports)}, ensure_ascii=False, indent=2))
    return 0


def _load_train_module() -> Any:
    spec = importlib.util.spec_from_file_location("train_price_baseline_model", TRAIN_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {TRAIN_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _horizon_breakdown(
    *,
    train_module: Any,
    horizon: int,
    rows: list[dict[str, float | str]],
    features: list[str],
    min_train_rows: int,
    samples_per_era: int,
) -> dict[str, Any]:
    windows = _eligible_windows(rows, min_train_rows)
    era_windows = _sample_eras(windows, samples_per_era)
    eras = {}
    for era_name, selected_windows in era_windows.items():
        predictions = []
        for _test_date, train_rows, test_rows in selected_windows:
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
            model = train_module._fit_linear_model(train_rows, usable_features)
            predictions.extend(train_module._prediction_rows(model, test_rows, threshold))
        by_item = _by_item(train_module, predictions)
        eras[era_name] = {
            "prediction_count": len(predictions),
            "overall": train_module._aggregate_prediction_metrics(predictions),
            "by_item": by_item,
            "weak_items": [
                item
                for item, metrics in by_item.items()
                if float(metrics.get("direction_accuracy", 0.0)) < 0.6
            ],
        }
    return {
        "horizon_days": horizon,
        "eligible_window_count": len(windows),
        "sampled_window_count": sum(len(windows) for windows in era_windows.values()),
        "eras": eras,
        "weakness": _weakness(eras),
    }


def _eligible_windows(rows: list[dict[str, float | str]], min_train_rows: int) -> list[tuple[str, list[Any], list[Any]]]:
    dates = sorted({str(row["base_date"]) for row in rows})
    windows = []
    for test_date in dates[1:]:
        train_rows = [row for row in rows if str(row["base_date"]) < test_date]
        test_rows = [row for row in rows if str(row["base_date"]) == test_date]
        if len(train_rows) >= min_train_rows and test_rows:
            windows.append((test_date, train_rows, test_rows))
    return windows


def _sample_eras(windows: list[Any], samples_per_era: int) -> dict[str, list[Any]]:
    count = len(windows)
    half = samples_per_era // 2
    middle_start = max(0, count // 2 - half)
    return {
        "early": windows[:samples_per_era],
        "middle": windows[middle_start : middle_start + samples_per_era],
        "recent": windows[-samples_per_era:],
    }


def _by_item(train_module: Any, predictions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for prediction in predictions:
        grouped.setdefault(str(prediction["item_code"]), []).append(prediction)
    return {
        item_code: {
            **train_module._aggregate_prediction_metrics(item_predictions),
            "prediction_count": len(item_predictions),
            "misses": [
                {
                    "base_date": row["base_date"],
                    "predicted_direction": row["predicted_direction"],
                    "actual_direction": row["actual_direction"],
                    "prediction": row["prediction"],
                    "actual": row["actual"],
                }
                for row in item_predictions
                if row["predicted_direction"] != row["actual_direction"]
            ][:10],
        }
        for item_code, item_predictions in sorted(grouped.items())
    }


def _weakness(eras: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for era_name, era in eras.items():
        for item_code, metrics in era.get("by_item", {}).items():
            if float(metrics.get("direction_accuracy", 0.0)) < 0.6:
                rows.append(
                    {
                        "era": era_name,
                        "item_code": item_code,
                        "direction_accuracy": metrics.get("direction_accuracy"),
                        "mae": metrics.get("mae"),
                        "prediction_count": metrics.get("prediction_count"),
                    }
                )
    return sorted(rows, key=lambda row: (float(row["direction_accuracy"]), str(row["era"]), str(row["item_code"])))


def _summary(reports: list[dict[str, Any]]) -> dict[str, Any]:
    weak_counts: dict[str, int] = {}
    for report in reports:
        for row in report.get("weakness", []):
            weak_counts[row["item_code"]] = weak_counts.get(row["item_code"], 0) + 1
    return {
        "horizon_count": len(reports),
        "weak_item_counts": dict(sorted(weak_counts.items(), key=lambda pair: (-pair[1], pair[0]))),
    }


def _parse_horizons(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
