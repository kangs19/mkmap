from __future__ import annotations

import argparse
import csv
import json
import math
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
        print(f"[WARN] Risk signal file not found, skipping overlays: {path}", file=sys.stderr)
        return {}

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
    active_model, model_scope = _select_model(model, row["item_code"])
    horizon_days = int(active_model.get("horizon_days") or model.get("horizon_days") or 1)
    target_column = str(active_model.get("target_column") or model.get("target_column") or "target_next_change")
    coefficients = active_model["coefficients"]
    feature_stats = active_model.get("feature_stats", {})
    assert isinstance(coefficients, dict)
    assert isinstance(feature_stats, dict)
    prediction = float(active_model["intercept"])
    for feature in active_model["features"]:
        stats = feature_stats.get(str(feature), {"mean": 0.0, "std": 1.0})
        assert isinstance(stats, dict)
        prediction += float(coefficients[str(feature)]) * _standardize(float(row[str(feature)]), stats)

    risk_score = float(risk_overlay.get("max_risk_score", 0.0)) if risk_overlay else 0.0
    risk_adjustment = max(0.0, min(1.0, risk_score)) * risk_adjustment_scale
    customs_adjustment, customs_overlay = _customs_trade_adjustment(row, horizon_days)
    adjusted_prediction = prediction + risk_adjustment + customs_adjustment
    direction_threshold = float(active_model.get("direction_threshold") or model.get("direction_threshold") or 0.015)

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

    calibration = model.get("probability_calibration") if isinstance(model.get("probability_calibration"), dict) else {}
    up_probability = _change_to_probability(adjusted_prediction, calibration, direction_threshold)
    surge_probability = _change_to_surge_probability(adjusted_prediction, calibration, direction_threshold)

    result = {
        "base_date": row["base_date"],
        "item_code": row["item_code"],
        "avg_price": float(row["avg_price"]),
        "model_scope": model_scope,
        "target_column": target_column,
        "horizon_days": horizon_days,
        "predicted_change": round(prediction, 6),
        "predicted_next_change": round(prediction, 6),
        "predicted_direction": direction,
        "direction_threshold": round(direction_threshold, 6),
        "risk_adjustment": round(risk_adjustment, 6),
        "customs_trade_adjustment": round(customs_adjustment, 6),
        "risk_adjusted_change": round(adjusted_prediction, 6),
        "risk_adjusted_next_change": round(adjusted_prediction, 6),
        "risk_adjusted_direction": adjusted_direction,
        f"up_probability_{horizon_days}d": up_probability,
        f"surge_probability_{horizon_days}d": surge_probability,
        "up_probability_14d": up_probability,
        "surge_probability_14d": surge_probability,
        "bottom_probability": round(1.0 - up_probability, 4),
        "confidence": str(calibration.get("confidence") or "low"),
        "probability_calibration": calibration,
    }
    if risk_overlay:
        result["risk_overlay"] = risk_overlay
    if customs_overlay:
        result["customs_trade_overlay"] = customs_overlay
    return result


def _select_model(model: dict[str, object], item_code: str) -> tuple[dict[str, object], str]:
    item_models = model.get("item_models")
    if isinstance(item_models, dict):
        item_model = item_models.get(item_code)
        if isinstance(item_model, dict):
            return item_model, "item"
    return model, "global"


def _standardize(value: float, stats: dict[str, object]) -> float:
    std = float(stats.get("std") or 1.0)
    if std == 0:
        std = 1.0
    return (value - float(stats.get("mean") or 0.0)) / std


def _customs_trade_adjustment(row: dict[str, str], horizon_days: int) -> tuple[float, dict[str, object] | None]:
    if horizon_days < 30:
        return 0.0, None

    item_code = row["item_code"]
    prefix = f"customs_{item_code}_"
    import_weight = _row_float(row, prefix + "import_weight_log")
    if import_weight <= 0:
        return 0.0, None

    pressure = (
        _row_float(row, prefix + "import_3m_pressure") * 0.5
        + _row_float(row, prefix + "import_yoy_change") * 0.3
        + _row_float(row, prefix + "import_mom_change") * 0.2
    )
    pressure = max(-1.0, min(1.0, pressure))
    scale = 0.012 if horizon_days <= 30 else 0.018 if horizon_days <= 90 else 0.024
    # Import growth usually adds domestic downside pressure; import contraction
    # removes substitute supply and can add upside pressure.
    adjustment = -pressure * scale
    overlay = {
        "item_code": item_code,
        "horizon_days": horizon_days,
        "import_pressure_score": round(pressure, 6),
        "adjustment": round(adjustment, 6),
        "direction_effect": "down" if adjustment < -0.0005 else "up" if adjustment > 0.0005 else "neutral",
        "basis": {
            "import_weight_log": round(import_weight, 6),
            "import_3m_pressure": round(_row_float(row, prefix + "import_3m_pressure"), 6),
            "import_yoy_change": round(_row_float(row, prefix + "import_yoy_change"), 6),
            "import_mom_change": round(_row_float(row, prefix + "import_mom_change"), 6),
        },
    }
    return adjustment, overlay


def _row_float(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _change_to_probability(change: float, calibration: dict[str, object], direction_threshold: float) -> float:
    scale = float(calibration.get("scale") or max(direction_threshold, 0.01))
    if scale <= 0:
        scale = max(direction_threshold, 0.01)
    probability = 0.5 + 0.45 * math.tanh(change / scale)
    return round(max(0.05, min(0.95, probability)), 4)


def _change_to_surge_probability(change: float, calibration: dict[str, object], direction_threshold: float) -> float:
    if change <= 0:
        return 0.0
    scale = float(calibration.get("scale") or max(direction_threshold, 0.01))
    surge_start = max(direction_threshold * 2.0, scale * 1.5, 0.03)
    surge_full = max(surge_start * 2.0, 0.08)
    probability = (change - surge_start) / max(surge_full - surge_start, 0.001)
    return round(max(0.0, min(1.0, probability)), 4)


if __name__ == "__main__":
    sys.exit(main())
