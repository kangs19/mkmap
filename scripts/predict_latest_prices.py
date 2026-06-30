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
    parser.add_argument("--signals", default=None, help="Optional region_risk_signals.json from export_live_signals.py")
    parser.add_argument("--risk-adjustment-scale", type=float, default=0.02, help="Max additive risk overlay for risk_score=1.0")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model = json.loads(Path(args.model).read_text(encoding="utf-8"))
    rows = _latest_rows_by_item(Path(args.features))
    risk_overlays = _load_risk_overlays(Path(args.signals)) if args.signals else {}
    predictions = [_predict_row(model, row, risk_overlays.get(row["item_code"]), args.risk_adjustment_scale) for row in rows]

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


def _load_risk_overlays(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"Risk signal file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    overlays: dict[str, dict[str, object]] = {}
    if not isinstance(payload, list):
        return overlays

    for item_payload in payload:
        if not isinstance(item_payload, dict):
            continue
        item_code = item_payload.get("item_code")
        signals = item_payload.get("signals")
        if not item_code or not isinstance(signals, list) or not signals:
            continue

        top_signal = max(
            (signal for signal in signals if isinstance(signal, dict)),
            key=lambda signal: float(signal.get("risk_score") or 0.0),
            default=None,
        )
        if not top_signal:
            continue
        top_factors = top_signal.get("top_factors") if isinstance(top_signal.get("top_factors"), list) else []
        overlays[str(item_code)] = {
            "max_risk_score": float(top_signal.get("risk_score") or 0.0),
            "risk_level": top_signal.get("risk_level"),
            "price_effect": top_signal.get("price_effect"),
            "top_region_code": top_signal.get("region_code"),
            "top_region_name": top_signal.get("region_name"),
            "top_factor": top_factors[0].get("factor") if top_factors and isinstance(top_factors[0], dict) else None,
            "data_status": item_payload.get("data_status") if isinstance(item_payload.get("data_status"), dict) else {},
        }
    return overlays


def _predict_row(
    model: dict[str, object],
    row: dict[str, str],
    risk_overlay: dict[str, object] | None = None,
    risk_adjustment_scale: float = 0.02,
) -> dict[str, object]:
    coefficients = model["coefficients"]
    feature_stats = model.get("feature_stats", {})
    assert isinstance(coefficients, dict)
    assert isinstance(feature_stats, dict)
    prediction = float(model["intercept"])
    for feature in model["features"]:
        stats = feature_stats.get(str(feature), {"mean": 0.0, "std": 1.0})
        assert isinstance(stats, dict)
        prediction += float(coefficients[str(feature)]) * _standardize(float(row[str(feature)]), stats)

    risk_score = float(risk_overlay.get("max_risk_score", 0.0)) if risk_overlay else 0.0
    risk_adjustment = max(0.0, min(1.0, risk_score)) * risk_adjustment_scale
    adjusted_prediction = prediction + risk_adjustment
    direction_threshold = float(model.get("direction_threshold") or 0.015)

    if prediction > direction_threshold:
        direction = "up"
    elif prediction < -direction_threshold:
        direction = "down"
    else:
        direction = "stable"

    if adjusted_prediction > direction_threshold:
        adjusted_direction = "up"
    elif adjusted_prediction < -direction_threshold:
        adjusted_direction = "down"
    else:
        adjusted_direction = "stable"

    result = {
        "base_date": row["base_date"],
        "item_code": row["item_code"],
        "avg_price": float(row["avg_price"]),
        "predicted_next_change": round(prediction, 6),
        "predicted_direction": direction,
        "direction_threshold": round(direction_threshold, 6),
        "risk_adjustment": round(risk_adjustment, 6),
        "risk_adjusted_next_change": round(adjusted_prediction, 6),
        "risk_adjusted_direction": adjusted_direction,
    }
    if risk_overlay:
        result["risk_overlay"] = risk_overlay
    return result


def _standardize(value: float, stats: dict[str, object]) -> float:
    std = float(stats.get("std") or 1.0)
    if std == 0:
        std = 1.0
    return (value - float(stats.get("mean") or 0.0)) / std


if __name__ == "__main__":
    sys.exit(main())
