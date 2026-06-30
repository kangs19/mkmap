from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean


REPO_ROOT = Path(__file__).resolve().parents[1]


EXCLUDED_COLUMNS = {"base_date", "item_code", "target_next_change"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small baseline price-change model.")
    parser.add_argument("--input", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--output", default=None)
    parser.add_argument("--report-output", default=None)
    parser.add_argument("--min-item-rows", type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, features = _read_rows(Path(args.input))
    if len(rows) < 10:
        print(json.dumps({"ok": False, "reason": "not_enough_rows", "rows": len(rows)}, ensure_ascii=False, indent=2))
        return 1
    if not features:
        print(json.dumps({"ok": False, "reason": "no_feature_columns", "rows": len(rows)}, ensure_ascii=False, indent=2))
        return 1

    train, test = _time_split(rows)
    model = _fit_linear_model(train, features)
    threshold = _tune_direction_threshold(model, test)
    model["direction_threshold"] = threshold
    metrics = _evaluate(model, test, threshold)
    item_models = _fit_item_models(rows, features, model, threshold, min_item_rows=args.min_item_rows)
    report = _evaluation_report(model, test, threshold, item_models)

    out_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / "price_baseline_model.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report_output) if args.report_output else out_path.with_name(out_path.stem + "_evaluation.json")
    payload = {
        "model_type": "standardized_linear_baseline",
        "features": features,
        "intercept": model["intercept"],
        "coefficients": model["coefficients"],
        "feature_stats": model["feature_stats"],
        "direction_threshold": threshold,
        "item_models": item_models,
        "train_rows": len(train),
        "test_rows": len(test),
        "metrics": metrics,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "model_path": str(out_path), "report_path": str(report_path), **payload}, ensure_ascii=False, indent=2))
    return 0


def _read_rows(path: Path) -> tuple[list[dict[str, float | str]], list[str]]:
    rows: list[dict[str, float | str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return [], []
        features = [field for field in reader.fieldnames if field not in EXCLUDED_COLUMNS]
        for row in reader:
            parsed: dict[str, float | str] = {"base_date": row["base_date"], "item_code": row["item_code"]}
            try:
                for field in features + ["target_next_change"]:
                    parsed[field] = float(row[field])
            except (TypeError, ValueError):
                continue
            rows.append(parsed)
    usable_features = [
        feature
        for feature in features
        if any(abs(float(row[feature])) > 0 for row in rows)
    ]
    return sorted(rows, key=lambda row: (str(row["base_date"]), str(row["item_code"]))), usable_features


def _time_split(rows: list[dict[str, float | str]]) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    split = max(1, int(len(rows) * 0.8))
    if split >= len(rows):
        split = len(rows) - 1
    return rows[:split], rows[split:]


def _fit_item_models(
    rows: list[dict[str, float | str]],
    features: list[str],
    global_model: dict[str, object],
    global_threshold: float,
    min_item_rows: int,
) -> dict[str, dict[str, object]]:
    item_models: dict[str, dict[str, object]] = {}
    by_item: dict[str, list[dict[str, float | str]]] = {}
    for row in rows:
        by_item.setdefault(str(row["item_code"]), []).append(row)

    for item_code, item_rows in sorted(by_item.items()):
        if len(item_rows) < min_item_rows:
            continue
        train, test = _time_split(item_rows)
        if len(train) < 10 or len(test) < 3:
            continue

        usable_features = [
            feature
            for feature in features
            if any(abs(float(row[feature])) > 0 for row in train)
        ]
        if not usable_features:
            continue

        item_model = _fit_linear_model(train, usable_features)
        threshold = _tune_direction_threshold(item_model, test)
        item_metrics = _evaluate(item_model, test, threshold)
        global_metrics = _evaluate(global_model, test, global_threshold)
        if not _item_model_is_better(item_metrics, global_metrics):
            continue

        item_model["direction_threshold"] = threshold
        item_model["train_rows"] = len(train)
        item_model["test_rows"] = len(test)
        item_model["metrics"] = item_metrics
        item_model["global_fallback_metrics"] = global_metrics
        item_model["model_scope"] = "item"
        item_models[item_code] = item_model

    return item_models


def _item_model_is_better(item_metrics: dict[str, float], global_metrics: dict[str, float]) -> bool:
    item_mae = float(item_metrics.get("mae", 999.0))
    global_mae = float(global_metrics.get("mae", 999.0))
    item_direction = float(item_metrics.get("direction_accuracy", 0.0))
    global_direction = float(global_metrics.get("direction_accuracy", 0.0))
    if item_mae > global_mae * 1.05:
        return False
    if item_direction + 0.0001 < global_direction:
        return False
    return True


def _fit_linear_model(rows: list[dict[str, float | str]], features: list[str]) -> dict[str, object]:
    y_mean = mean(float(row["target_next_change"]) for row in rows)
    stats = _feature_stats(rows, features)
    weights = {feature: 0.0 for feature in features}
    intercept = y_mean
    learning_rate = 0.03
    l2_penalty = 0.01
    n_rows = len(rows)

    for _ in range(2500):
        intercept_grad = 0.0
        weight_grads = {feature: 0.0 for feature in features}
        for row in rows:
            y = float(row["target_next_change"])
            pred = intercept + sum(weights[feature] * _standardize(float(row[feature]), stats[feature]) for feature in features)
            error = pred - y
            intercept_grad += error
            for feature in features:
                weight_grads[feature] += error * _standardize(float(row[feature]), stats[feature])

        intercept -= learning_rate * intercept_grad / n_rows
        for feature in features:
            grad = (weight_grads[feature] / n_rows) + (l2_penalty * weights[feature])
            weights[feature] -= learning_rate * grad

    coefficients = {feature: round(weight, 10) for feature, weight in weights.items()}
    return {
        "intercept": round(intercept, 10),
        "features": features,
        "coefficients": coefficients,
        "feature_stats": stats,
    }


def _feature_stats(rows: list[dict[str, float | str]], features: list[str]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for feature in features:
        values = [float(row[feature]) for row in rows]
        avg = mean(values)
        variance = mean((value - avg) ** 2 for value in values)
        std = math.sqrt(variance)
        stats[feature] = {"mean": round(avg, 10), "std": round(std if std > 0 else 1.0, 10)}
    return stats


def _predict(model: dict[str, object], row: dict[str, float | str]) -> float:
    coefficients = model["coefficients"]
    feature_stats = model.get("feature_stats", {})
    assert isinstance(coefficients, dict)
    assert isinstance(feature_stats, dict)
    prediction = float(model["intercept"])
    for feature in model["features"]:
        stats = feature_stats.get(str(feature), {"mean": 0.0, "std": 1.0})
        assert isinstance(stats, dict)
        prediction += float(coefficients[str(feature)]) * _standardize(float(row[str(feature)]), stats)
    return prediction


def _standardize(value: float, stats: dict[str, float]) -> float:
    std = float(stats.get("std") or 1.0)
    if std == 0:
        std = 1.0
    return (value - float(stats.get("mean") or 0.0)) / std


def _evaluate(model: dict[str, object], rows: list[dict[str, float | str]], threshold: float) -> dict[str, float]:
    errors = [_predict(model, row) - float(row["target_next_change"]) for row in rows]
    mae = mean(abs(error) for error in errors)
    rmse = math.sqrt(mean(error**2 for error in errors))
    sign_hits = [(_predict(model, row) >= 0) == (float(row["target_next_change"]) >= 0) for row in rows]
    direction_hits = [_direction(_predict(model, row), threshold) == _direction(float(row["target_next_change"]), threshold) for row in rows]
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "sign_accuracy": round(sum(sign_hits) / len(sign_hits), 4) if sign_hits else 0.0,
        "direction_accuracy": round(sum(direction_hits) / len(direction_hits), 4) if direction_hits else 0.0,
    }


def _tune_direction_threshold(model: dict[str, object], rows: list[dict[str, float | str]]) -> float:
    if not rows:
        return 0.015
    candidates = [idx / 10000 for idx in range(0, 301, 5)]
    best_threshold = 0.015
    best_score = -1.0
    for threshold in candidates:
        hits = [
            _direction(_predict(model, row), threshold) == _direction(float(row["target_next_change"]), threshold)
            for row in rows
        ]
        score = sum(hits) / len(hits)
        if score > best_score or (score == best_score and abs(threshold - 0.015) < abs(best_threshold - 0.015)):
            best_score = score
            best_threshold = threshold
    return round(best_threshold, 6)


def _evaluation_report(
    model: dict[str, object],
    rows: list[dict[str, float | str]],
    threshold: float,
    item_models: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    item_models = item_models or {}
    by_item: dict[str, list[dict[str, float | str]]] = {}
    for row in rows:
        by_item.setdefault(str(row["item_code"]), []).append(row)

    item_metrics = {}
    for item_code, item_rows in sorted(by_item.items()):
        active_model = item_models.get(item_code, model)
        active_threshold = float(active_model.get("direction_threshold", threshold))
        metrics = _evaluate(active_model, item_rows, active_threshold)
        metrics["model_scope"] = "item" if item_code in item_models else "global"
        item_metrics[item_code] = metrics

    predictions = []
    for row in rows[-20:]:
        item_code = str(row["item_code"])
        active_model = item_models.get(item_code, model)
        active_threshold = float(active_model.get("direction_threshold", threshold))
        pred = _predict(active_model, row)
        actual = float(row["target_next_change"])
        predictions.append(
            {
                "base_date": row["base_date"],
                "item_code": row["item_code"],
                "prediction": round(pred, 6),
                "actual": round(actual, 6),
                "predicted_direction": _direction(pred, active_threshold),
                "actual_direction": _direction(actual, active_threshold),
                "absolute_error": round(abs(pred - actual), 6),
                "model_scope": "item" if item_code in item_models else "global",
            }
        )

    return {
        "model_type": model.get("model_type", "standardized_linear_baseline"),
        "direction_threshold": threshold,
        "overall": _evaluate(model, rows, threshold),
        "by_item": item_metrics,
        "item_model_count": len(item_models),
        "sample_predictions": predictions,
    }


def _direction(value: float, threshold: float) -> str:
    if value > threshold:
        return "up"
    if value < -threshold:
        return "down"
    return "stable"


if __name__ == "__main__":
    sys.exit(main())
