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
    parser.add_argument("--backtest-output", default=None)
    parser.add_argument("--backtest-min-train-rows", type=int, default=24)
    parser.add_argument("--backtest-window-count", type=int, default=8)
    parser.add_argument("--min-item-rows", type=int, default=24)
    parser.add_argument("--item-model-max-mae-ratio", type=float, default=1.0)
    parser.add_argument("--item-model-short-history-rows", type=int, default=45)
    parser.add_argument("--item-model-short-history-min-mae-ratio", type=float, default=0.95)
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
    item_models = _fit_item_models(
        rows,
        features,
        model,
        threshold,
        min_item_rows=args.min_item_rows,
        max_mae_ratio=args.item_model_max_mae_ratio,
        short_history_rows=args.item_model_short_history_rows,
        short_history_min_mae_ratio=args.item_model_short_history_min_mae_ratio,
    )
    backtest = _rolling_backtest(
        rows,
        features,
        min_train_rows=args.backtest_min_train_rows,
        max_windows=args.backtest_window_count,
    )
    report = _evaluation_report(model, test, threshold, item_models, backtest)

    out_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / "price_baseline_model.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report_output) if args.report_output else out_path.with_name(out_path.stem + "_evaluation.json")
    backtest_path = Path(args.backtest_output) if args.backtest_output else out_path.with_name(out_path.stem + "_backtest.json")
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
        "probability_calibration": _probability_calibration(backtest, threshold),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    backtest_path.write_text(json.dumps(backtest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "model_path": str(out_path),
                "report_path": str(report_path),
                "backtest_path": str(backtest_path),
                **payload,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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
    max_mae_ratio: float,
    short_history_rows: int,
    short_history_min_mae_ratio: float,
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
        acceptance_gate = _item_acceptance_gate(
            item_metrics,
            global_metrics,
            item_rows=len(item_rows),
            max_mae_ratio=max_mae_ratio,
            short_history_rows=short_history_rows,
            short_history_min_mae_ratio=short_history_min_mae_ratio,
        )
        if not acceptance_gate["accepted"]:
            continue

        item_model["direction_threshold"] = threshold
        item_model["train_rows"] = len(train)
        item_model["test_rows"] = len(test)
        item_model["metrics"] = item_metrics
        item_model["global_fallback_metrics"] = global_metrics
        item_model["acceptance_gate"] = acceptance_gate
        item_model["model_scope"] = "item"
        item_models[item_code] = item_model

    return item_models


def _item_acceptance_gate(
    item_metrics: dict[str, float],
    global_metrics: dict[str, float],
    item_rows: int,
    max_mae_ratio: float,
    short_history_rows: int,
    short_history_min_mae_ratio: float,
) -> dict[str, object]:
    item_mae = float(item_metrics.get("mae", 999.0))
    global_mae = float(global_metrics.get("mae", 999.0))
    item_direction = float(item_metrics.get("direction_accuracy", 0.0))
    global_direction = float(global_metrics.get("direction_accuracy", 0.0))
    effective_global_mae = max(global_mae, 0.000001)
    mae_ratio = item_mae / effective_global_mae
    short_history = item_rows < short_history_rows
    direction_gain = item_direction - global_direction

    accepted = True
    reason = "accepted"
    if mae_ratio > max_mae_ratio:
        accepted = False
        reason = "mae_worse_than_global"
    elif item_direction + 0.0001 < global_direction:
        accepted = False
        reason = "direction_worse_than_global"
    elif short_history and direction_gain <= 0.0001 and mae_ratio > short_history_min_mae_ratio:
        accepted = False
        reason = "short_history_without_clear_gain"

    return {
        "accepted": accepted,
        "reason": reason,
        "item_rows": item_rows,
        "short_history": short_history,
        "mae_ratio_vs_global": round(mae_ratio, 6),
        "direction_gain_vs_global": round(direction_gain, 6),
        "max_mae_ratio": max_mae_ratio,
        "short_history_rows": short_history_rows,
        "short_history_min_mae_ratio": short_history_min_mae_ratio,
    }


def _rolling_backtest(
    rows: list[dict[str, float | str]],
    features: list[str],
    min_train_rows: int,
    max_windows: int,
) -> dict[str, object]:
    dates = sorted({str(row["base_date"]) for row in rows})
    eligible_windows = []
    for test_date in dates[1:]:
        train_rows = [row for row in rows if str(row["base_date"]) < test_date]
        test_rows = [row for row in rows if str(row["base_date"]) == test_date]
        if len(train_rows) >= min_train_rows and test_rows:
            eligible_windows.append((test_date, train_rows, test_rows))

    windows = []
    for test_date, train_rows, test_rows in eligible_windows[-max_windows:]:
        usable_features = [
            feature
            for feature in features
            if any(abs(float(row[feature])) > 0 for row in train_rows)
        ]
        if len(train_rows) < 10 or not usable_features:
            continue

        threshold = 0.015
        inner_train, validation = _time_split(train_rows)
        if len(inner_train) >= 10 and validation:
            threshold = _tune_direction_threshold(_fit_linear_model(inner_train, usable_features), validation)

        window_model = _fit_linear_model(train_rows, usable_features)
        predictions = _prediction_rows(window_model, test_rows, threshold)
        windows.append(
            {
                "test_date": test_date,
                "train_rows": len(train_rows),
                "test_rows": len(test_rows),
                "feature_count": len(usable_features),
                "direction_threshold": threshold,
                "metrics": _aggregate_prediction_metrics(predictions),
                "predictions": predictions,
            }
        )

    all_predictions = [prediction for window in windows for prediction in window["predictions"]]
    summary = _aggregate_prediction_metrics(all_predictions)
    summary["window_count"] = len(windows)
    summary["prediction_count"] = len(all_predictions)
    summary["min_train_rows"] = min_train_rows
    summary["max_window_count"] = max_windows
    summary["by_item"] = _aggregate_predictions_by_item(all_predictions)
    return {"summary": summary, "windows": windows}


def _probability_calibration(backtest: dict[str, object], direction_threshold: float) -> dict[str, object]:
    summary = backtest.get("summary") if isinstance(backtest.get("summary"), dict) else {}
    mae = float(summary.get("mae") or 0.0)
    direction_accuracy = float(summary.get("direction_accuracy") or 0.0)
    prediction_count = int(summary.get("prediction_count") or 0)
    scale = max(direction_threshold, mae * 2.0, 0.01)
    if prediction_count < 10:
        confidence = "low"
    elif direction_accuracy >= 0.65 and mae <= scale:
        confidence = "high"
    elif direction_accuracy >= 0.55:
        confidence = "medium"
    else:
        confidence = "low"
    return {
        "method": "rolling_backtest_error_scaled_tanh",
        "scale": round(scale, 6),
        "mae": round(mae, 6),
        "direction_accuracy": round(direction_accuracy, 4),
        "prediction_count": prediction_count,
        "confidence": confidence,
    }


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


def _prediction_rows(
    model: dict[str, object],
    rows: list[dict[str, float | str]],
    threshold: float,
) -> list[dict[str, object]]:
    predictions = []
    for row in rows:
        pred = _predict(model, row)
        actual = float(row["target_next_change"])
        predictions.append(
            {
                "base_date": row["base_date"],
                "item_code": row["item_code"],
                "prediction": round(pred, 6),
                "actual": round(actual, 6),
                "predicted_direction": _direction(pred, threshold),
                "actual_direction": _direction(actual, threshold),
                "absolute_error": round(abs(pred - actual), 6),
            }
        )
    return predictions


def _aggregate_prediction_metrics(predictions: list[dict[str, object]]) -> dict[str, float]:
    if not predictions:
        return {"mae": 0.0, "rmse": 0.0, "sign_accuracy": 0.0, "direction_accuracy": 0.0}

    errors = [float(row["prediction"]) - float(row["actual"]) for row in predictions]
    sign_hits = [
        (float(row["prediction"]) >= 0) == (float(row["actual"]) >= 0)
        for row in predictions
    ]
    direction_hits = [
        str(row["predicted_direction"]) == str(row["actual_direction"])
        for row in predictions
    ]
    return {
        "mae": round(mean(abs(error) for error in errors), 6),
        "rmse": round(math.sqrt(mean(error**2 for error in errors)), 6),
        "sign_accuracy": round(sum(sign_hits) / len(sign_hits), 4),
        "direction_accuracy": round(sum(direction_hits) / len(direction_hits), 4),
    }


def _aggregate_predictions_by_item(predictions: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    by_item: dict[str, list[dict[str, object]]] = {}
    for prediction in predictions:
        by_item.setdefault(str(prediction["item_code"]), []).append(prediction)
    return {
        item_code: {
            **_aggregate_prediction_metrics(item_predictions),
            "prediction_count": len(item_predictions),
        }
        for item_code, item_predictions in sorted(by_item.items())
    }


def _evaluation_report(
    model: dict[str, object],
    rows: list[dict[str, float | str]],
    threshold: float,
    item_models: dict[str, dict[str, object]] | None = None,
    backtest: dict[str, object] | None = None,
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
        "rolling_backtest": (backtest or {}).get("summary", {}),
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
