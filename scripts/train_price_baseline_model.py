from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from statistics import mean


REPO_ROOT = Path(__file__).resolve().parents[1]


FEATURES = ["change_1d", "change_3d"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a small baseline price-change model.")
    parser.add_argument("--input", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = _read_rows(Path(args.input))
    if len(rows) < 10:
        print(json.dumps({"ok": False, "reason": "not_enough_rows", "rows": len(rows)}, ensure_ascii=False, indent=2))
        return 1

    train, test = _time_split(rows)
    model = _fit_linear_model(train)
    metrics = _evaluate(model, test)

    out_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / "price_baseline_model.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_type": "linear_baseline",
        "features": FEATURES,
        "intercept": model["intercept"],
        "coefficients": model["coefficients"],
        "train_rows": len(train),
        "test_rows": len(test),
        "metrics": metrics,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "model_path": str(out_path), **payload}, ensure_ascii=False, indent=2))
    return 0


def _read_rows(path: Path) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed: dict[str, float | str] = {"base_date": row["base_date"], "item_code": row["item_code"]}
            for field in FEATURES + ["target_next_change"]:
                parsed[field] = float(row[field])
            rows.append(parsed)
    return sorted(rows, key=lambda row: (str(row["base_date"]), str(row["item_code"])))


def _time_split(rows: list[dict[str, float | str]]) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    split = max(1, int(len(rows) * 0.8))
    if split >= len(rows):
        split = len(rows) - 1
    return rows[:split], rows[split:]


def _fit_linear_model(rows: list[dict[str, float | str]]) -> dict[str, object]:
    y_mean = mean(float(row["target_next_change"]) for row in rows)
    coefficients: dict[str, float] = {}
    for feature in FEATURES:
        xs = [float(row[feature]) for row in rows]
        ys = [float(row["target_next_change"]) for row in rows]
        x_mean = mean(xs)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        denominator = sum((x - x_mean) ** 2 for x in xs)
        coefficients[feature] = 0.0 if denominator == 0 else numerator / denominator

    intercept = y_mean - sum(coefficients[feature] * mean(float(row[feature]) for row in rows) for feature in FEATURES)
    return {"intercept": intercept, "coefficients": coefficients}


def _predict(model: dict[str, object], row: dict[str, float | str]) -> float:
    coefficients = model["coefficients"]
    assert isinstance(coefficients, dict)
    return float(model["intercept"]) + sum(float(coefficients[feature]) * float(row[feature]) for feature in FEATURES)


def _evaluate(model: dict[str, object], rows: list[dict[str, float | str]]) -> dict[str, float]:
    errors = [_predict(model, row) - float(row["target_next_change"]) for row in rows]
    mae = mean(abs(error) for error in errors)
    rmse = math.sqrt(mean(error**2 for error in errors))
    direction_hits = [
        (_predict(model, row) >= 0) == (float(row["target_next_change"]) >= 0)
        for row in rows
    ]
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "direction_accuracy": round(sum(direction_hits) / len(direction_hits), 4) if direction_hits else 0.0,
    }


if __name__ == "__main__":
    sys.exit(main())
