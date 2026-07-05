from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit quality consistency across horizon-specific price models.")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-backtest-direction", type=float, default=0.70)
    parser.add_argument("--min-test-direction", type=float, default=0.60)
    parser.add_argument("--max-direction-spread", type=float, default=0.20)
    parser.add_argument("--min-backtest-predictions", type=int, default=100)
    parser.add_argument("--robustness-report", default=None, help="Optional JSON from audit_price_model_robustness.py")
    parser.add_argument(
        "--temporal-policy",
        choices=("off", "warn", "hold"),
        default="warn",
        help="How to apply temporal-era robustness risk when a robustness report is supplied.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models_dir = Path(args.models_dir)
    rows = [_model_quality(path) for path in sorted(models_dir.glob(f"{args.model_prefix}_*d.json"))]
    rows = [row for row in rows if row]
    robustness_by_horizon = _load_robustness_report(Path(args.robustness_report)) if args.robustness_report else {}
    for row in rows:
        row["temporal_robustness"] = robustness_by_horizon.get(int(row["horizon_days"]), {})
    report = _quality_report(rows, args)
    out_path = Path(args.output) if args.output else models_dir / f"{args.model_prefix}_quality.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**report, "output": str(out_path)}, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def _model_quality(path: Path) -> dict[str, Any] | None:
    model = json.loads(path.read_text(encoding="utf-8"))
    horizon = model.get("horizon_days")
    if horizon is None:
        return None
    backtest_path = path.with_name(path.stem + "_backtest.json")
    backtest = json.loads(backtest_path.read_text(encoding="utf-8")) if backtest_path.exists() else {}
    bt_summary = backtest.get("summary") if isinstance(backtest.get("summary"), dict) else {}
    return {
        "horizon_days": int(horizon),
        "model_path": str(path),
        "target_column": model.get("target_column"),
        "train_rows": model.get("train_rows"),
        "test_rows": model.get("test_rows"),
        "test_direction_accuracy": _float(model.get("metrics", {}).get("direction_accuracy")),
        "test_mae": _float(model.get("metrics", {}).get("mae")),
        "backtest_direction_accuracy": _float(bt_summary.get("direction_accuracy")),
        "backtest_mae": _float(bt_summary.get("mae")),
        "backtest_prediction_count": int(bt_summary.get("prediction_count") or 0),
        "calibration_confidence": (model.get("probability_calibration") or {}).get("confidence"),
    }


def _quality_report(rows: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: int(row["horizon_days"]))
    backtest_scores = [row["backtest_direction_accuracy"] for row in rows if row["backtest_direction_accuracy"] is not None]
    test_scores = [row["test_direction_accuracy"] for row in rows if row["test_direction_accuracy"] is not None]
    backtest_spread = max(backtest_scores) - min(backtest_scores) if backtest_scores else None
    test_spread = max(test_scores) - min(test_scores) if test_scores else None

    findings = []
    for row in rows:
        reasons = []
        warnings = []
        if row["backtest_prediction_count"] < args.min_backtest_predictions:
            reasons.append("not_enough_backtest_predictions")
        if (row["backtest_direction_accuracy"] or 0.0) < args.min_backtest_direction:
            reasons.append("low_backtest_direction_accuracy")
        if (row["test_direction_accuracy"] or 0.0) < args.min_test_direction:
            reasons.append("low_test_direction_accuracy")
        temporal = row.get("temporal_robustness") if isinstance(row.get("temporal_robustness"), dict) else {}
        temporal_risk = str(temporal.get("risk_level") or "")
        if args.temporal_policy != "off" and temporal_risk in {"high", "medium"}:
            risk_reason = f"temporal_{temporal_risk}_risk"
            warnings.append(risk_reason)
            if args.temporal_policy == "hold":
                reasons.append(risk_reason)
        if reasons:
            row["promotion_status"] = "hold"
        elif warnings:
            row["promotion_status"] = "conditional"
        else:
            row["promotion_status"] = "candidate"
        row["hold_reasons"] = reasons
        row["warnings"] = warnings
        if reasons or warnings:
            findings.append(
                {
                    "horizon_days": row["horizon_days"],
                    "status": row["promotion_status"],
                    "reasons": reasons,
                    "warnings": warnings,
                    "test_direction_accuracy": row["test_direction_accuracy"],
                    "backtest_direction_accuracy": row["backtest_direction_accuracy"],
                    "temporal_risk_level": temporal_risk or None,
                }
            )

    consistency_reasons = []
    if backtest_spread is not None and backtest_spread > args.max_direction_spread:
        consistency_reasons.append("backtest_direction_spread_too_wide")
    if test_spread is not None and test_spread > args.max_direction_spread:
        consistency_reasons.append("test_direction_spread_too_wide")

    candidates = [row for row in rows if row["promotion_status"] in {"candidate", "conditional"}]
    holds = [row for row in rows if row["promotion_status"] == "hold"]
    warning_findings = [finding for finding in findings if finding["status"] == "conditional"]
    hold_findings = [finding for finding in findings if finding["status"] == "hold"]
    ok = bool(rows) and not hold_findings and not consistency_reasons
    return {
        "ok": ok,
        "model_prefix": args.model_prefix,
        "thresholds": {
            "min_backtest_direction": args.min_backtest_direction,
            "min_test_direction": args.min_test_direction,
            "max_direction_spread": args.max_direction_spread,
            "min_backtest_predictions": args.min_backtest_predictions,
        },
        "summary": {
            "horizon_count": len(rows),
            "candidate_count": len(candidates),
            "strict_candidate_count": len([row for row in rows if row["promotion_status"] == "candidate"]),
            "conditional_count": len([row for row in rows if row["promotion_status"] == "conditional"]),
            "hold_count": len(holds),
            "mean_test_direction_accuracy": round(mean(test_scores), 4) if test_scores else None,
            "mean_backtest_direction_accuracy": round(mean(backtest_scores), 4) if backtest_scores else None,
            "test_direction_spread": round(test_spread, 4) if test_spread is not None else None,
            "backtest_direction_spread": round(backtest_spread, 4) if backtest_spread is not None else None,
            "test_direction_std": round(pstdev(test_scores), 4) if len(test_scores) > 1 else 0.0,
            "backtest_direction_std": round(pstdev(backtest_scores), 4) if len(backtest_scores) > 1 else 0.0,
        },
        "temporal_policy": args.temporal_policy,
        "consistency_reasons": consistency_reasons,
        "findings": findings,
        "hold_findings": hold_findings,
        "warning_findings": warning_findings,
        "horizons": rows,
    }


def _load_robustness_report(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for row in payload.get("horizons", []):
        if not isinstance(row, dict):
            continue
        try:
            horizon = int(row["horizon_days"])
        except (KeyError, TypeError, ValueError):
            continue
        result[horizon] = {
            "risk_level": row.get("risk_level"),
            "risk_reasons": row.get("risk_reasons", []),
            "overfit_gap": row.get("overfit_gap", {}),
            "temporal_backtest": row.get("temporal_backtest", {}),
        }
    return result


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


if __name__ == "__main__":
    raise SystemExit(main())
