from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict next price change by item from the latest feature rows.")
    parser.add_argument("--features", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--model", required=True, help="JSON from train_price_baseline_model.py")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    rows = _latest_rows_by_item(Path(args.features))
    predictions = [_predict_row(model, row) for row in rows]

    out_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / "latest_price_predictions.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "prediction_path": str(out_path), "predictions": predictions}, ensure_ascii=False, indent=2))
    return 0


def _latest_rows_by_item(path: Path) -> list[dict[str, str]]:
    rows_by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows_by_item[row["item_code"]].append(row)
    return [
        sorted(rows, key=lambda row: row["base_date"])[-1]
        for _, rows in sorted(rows_by_item.items())
        if rows
    ]


def _predict_row(model: dict[str, object], row: dict[str, str]) -> dict[str, object]:
    coefficients = model["coefficients"]
    assert isinstance(coefficients, dict)
    prediction = float(model["intercept"])
    for feature in model["features"]:
        prediction += float(coefficients[str(feature)]) * float(row[str(feature)])

    if prediction > 0.015:
        direction = "up"
    elif prediction < -0.015:
        direction = "down"
    else:
        direction = "stable"

    return {
        "base_date": row["base_date"],
        "item_code": row["item_code"],
        "avg_price": float(row["avg_price"]),
        "predicted_next_change": round(prediction, 6),
        "predicted_direction": direction,
    }


if __name__ == "__main__":
    sys.exit(main())
