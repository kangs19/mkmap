from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create combined latest predictions from horizon-specific models.")
    parser.add_argument("--features", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--horizons", default="1,7,14,30,90,180,365")
    parser.add_argument("--signals", default=None)
    parser.add_argument("--quality-report", default=None, help="Optional JSON from audit_price_horizon_quality.py")
    parser.add_argument("--only-candidates", action="store_true", help="Skip horizons held by the quality report")
    parser.add_argument("--risk-adjustment-scale", type=float, default=0.02)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models_dir = Path(args.models_dir)
    combined: dict[str, dict[str, object]] = {}
    raw_outputs = []
    quality_by_horizon = _load_quality_report(Path(args.quality_report)) if args.quality_report else {}

    for horizon in _parse_horizons(args.horizons):
        quality = quality_by_horizon.get(horizon, {})
        promotion_status = str(quality.get("promotion_status") or "unchecked")
        if args.only_candidates and promotion_status not in {"candidate", "conditional", "unchecked"}:
            raw_outputs.append(
                {
                    "horizon_days": horizon,
                    "status": "skipped_by_quality_gate",
                    "promotion_status": promotion_status,
                    "hold_reasons": quality.get("hold_reasons", []),
                }
            )
            continue
        model_path = models_dir / f"{args.model_prefix}_{horizon}d.json"
        if not model_path.exists():
            continue
        temp_stem = Path(args.output).stem if args.output else "latest_price_horizon_predictions"
        temp_output = models_dir / f".{temp_stem}_{os.getpid()}_{horizon}d.tmp.json"
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "predict_latest_prices.py"),
            "--features",
            args.features,
            "--model",
            str(model_path),
            "--risk-adjustment-scale",
            str(args.risk_adjustment_scale),
            "--output",
            str(temp_output),
        ]
        if args.signals:
            command.extend(["--signals", args.signals])
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        if completed.returncode != 0:
            raw_outputs.append({"horizon_days": horizon, "status": "failed", "stderr": completed.stderr[-2000:]})
            continue
        predictions = json.loads(temp_output.read_text(encoding="utf-8"))
        temp_output.unlink(missing_ok=True)
        raw_outputs.append({"horizon_days": horizon, "status": "predicted", "prediction_count": len(predictions)})
        for prediction in predictions:
            item_code = str(prediction["item_code"])
            item = combined.setdefault(
                item_code,
                {
                    "base_date": prediction["base_date"],
                    "item_code": item_code,
                    "avg_price": prediction["avg_price"],
                    "horizons": {},
                },
            )
            horizons = item["horizons"]
            assert isinstance(horizons, dict)
            horizons[str(horizon)] = {
                "target_column": prediction.get("target_column"),
                "promotion_status": promotion_status,
                "hold_reasons": quality.get("hold_reasons", []),
                "predicted_change": prediction.get("predicted_change"),
                "risk_adjusted_change": prediction.get("risk_adjusted_change"),
                "predicted_direction": prediction.get("predicted_direction"),
                "risk_adjusted_direction": prediction.get("risk_adjusted_direction"),
                "direction_threshold": prediction.get("direction_threshold"),
                "up_probability": prediction.get(f"up_probability_{horizon}d"),
                "surge_probability": prediction.get(f"surge_probability_{horizon}d"),
                "confidence": prediction.get("confidence"),
                "model_scope": prediction.get("model_scope"),
            }

    output_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / "latest_price_horizon_predictions.json"
    payload = {
        "ok": True,
        "items": [combined[item_code] for item_code in sorted(combined)],
        "runs": raw_outputs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "prediction_path": str(output_path)}, ensure_ascii=False, indent=2))
    return 0


def _parse_horizons(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _load_quality_report(path: Path) -> dict[int, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    horizons = payload.get("horizons") if isinstance(payload, dict) else []
    if not isinstance(horizons, list):
        return {}
    result = {}
    for row in horizons:
        if not isinstance(row, dict):
            continue
        try:
            horizon = int(row["horizon_days"])
        except (KeyError, TypeError, ValueError):
            continue
        result[horizon] = row
    return result


if __name__ == "__main__":
    sys.exit(main())
