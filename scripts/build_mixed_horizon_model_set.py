from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an approved mixed horizon model set from baseline and candidate models.")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--baseline-prefix", required=True)
    parser.add_argument("--candidate-prefix", required=True)
    parser.add_argument("--approved-prefix", required=True)
    parser.add_argument("--horizons", default="1,14,30,180,365")
    parser.add_argument("--min-test-direction-gain", type=float, default=0.0)
    parser.add_argument("--min-backtest-direction-gain", type=float, default=0.0)
    parser.add_argument("--max-mae-regression", type=float, default=0.0)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models_dir = Path(args.models_dir)
    horizons = [int(part.strip()) for part in args.horizons.split(",") if part.strip()]
    rows = []
    for horizon in horizons:
        baseline = _load_bundle(models_dir, args.baseline_prefix, horizon)
        candidate = _load_bundle(models_dir, args.candidate_prefix, horizon)
        decision = _decision(
            baseline=baseline,
            candidate=candidate,
            min_test_direction_gain=args.min_test_direction_gain,
            min_backtest_direction_gain=args.min_backtest_direction_gain,
            max_mae_regression=args.max_mae_regression,
        )
        source_prefix = args.candidate_prefix if decision["approved_source"] == "candidate" else args.baseline_prefix
        _copy_bundle(models_dir, source_prefix, args.approved_prefix, horizon)
        rows.append(
            {
                "horizon_days": horizon,
                **decision,
                "baseline": _metrics_snapshot(baseline),
                "candidate": _metrics_snapshot(candidate),
            }
        )

    payload = {
        "ok": True,
        "approved_prefix": args.approved_prefix,
        "baseline_prefix": args.baseline_prefix,
        "candidate_prefix": args.candidate_prefix,
        "rules": {
            "min_test_direction_gain": args.min_test_direction_gain,
            "min_backtest_direction_gain": args.min_backtest_direction_gain,
            "max_mae_regression": args.max_mae_regression,
        },
        "horizons": rows,
    }
    output = Path(args.output) if args.output else models_dir / f"{args.approved_prefix}_approval_report.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "output": str(output)}, ensure_ascii=False, indent=2))
    return 0


def _load_bundle(models_dir: Path, prefix: str, horizon: int) -> dict[str, Any]:
    model_path = models_dir / f"{prefix}_{horizon}d.json"
    backtest_path = models_dir / f"{prefix}_{horizon}d_backtest.json"
    if not model_path.exists() or not backtest_path.exists():
        return {"exists": False}
    return {
        "exists": True,
        "model": json.loads(model_path.read_text(encoding="utf-8")),
        "backtest": json.loads(backtest_path.read_text(encoding="utf-8")),
    }


def _decision(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    min_test_direction_gain: float,
    min_backtest_direction_gain: float,
    max_mae_regression: float,
) -> dict[str, Any]:
    if not candidate.get("exists"):
        return {"approved_source": "baseline", "reason": "candidate_missing"}
    baseline_metrics = _metrics_snapshot(baseline)
    candidate_metrics = _metrics_snapshot(candidate)
    test_gain = candidate_metrics["test_direction_accuracy"] - baseline_metrics["test_direction_accuracy"]
    backtest_gain = candidate_metrics["backtest_direction_accuracy"] - baseline_metrics["backtest_direction_accuracy"]
    test_mae_delta = candidate_metrics["test_mae"] - baseline_metrics["test_mae"]
    backtest_mae_delta = candidate_metrics["backtest_mae"] - baseline_metrics["backtest_mae"]
    accepted = (
        test_gain >= min_test_direction_gain
        and backtest_gain >= min_backtest_direction_gain
        and test_mae_delta <= max_mae_regression
        and backtest_mae_delta <= max_mae_regression
    )
    if accepted:
        reason = "candidate_meets_comparison_rules"
    else:
        failed = []
        if test_gain < min_test_direction_gain:
            failed.append("test_direction_gain")
        if backtest_gain < min_backtest_direction_gain:
            failed.append("backtest_direction_gain")
        if test_mae_delta > max_mae_regression:
            failed.append("test_mae_regression")
        if backtest_mae_delta > max_mae_regression:
            failed.append("backtest_mae_regression")
        reason = "candidate_failed_" + "_".join(failed)
    return {
        "approved_source": "candidate" if accepted else "baseline",
        "reason": reason,
        "deltas": {
            "test_direction_gain": round(test_gain, 6),
            "backtest_direction_gain": round(backtest_gain, 6),
            "test_mae_delta": round(test_mae_delta, 6),
            "backtest_mae_delta": round(backtest_mae_delta, 6),
        },
    }


def _metrics_snapshot(bundle: dict[str, Any]) -> dict[str, float]:
    if not bundle.get("exists"):
        return {
            "test_direction_accuracy": 0.0,
            "test_mae": 999.0,
            "backtest_direction_accuracy": 0.0,
            "backtest_mae": 999.0,
        }
    model_metrics = bundle["model"].get("metrics", {})
    backtest_summary = bundle["backtest"].get("summary", {})
    return {
        "test_direction_accuracy": float(model_metrics.get("direction_accuracy") or 0.0),
        "test_mae": float(model_metrics.get("mae") or 999.0),
        "backtest_direction_accuracy": float(backtest_summary.get("direction_accuracy") or 0.0),
        "backtest_mae": float(backtest_summary.get("mae") or 999.0),
    }


def _copy_bundle(models_dir: Path, source_prefix: str, approved_prefix: str, horizon: int) -> None:
    for suffix in (".json", "_evaluation.json", "_backtest.json"):
        source = models_dir / f"{source_prefix}_{horizon}d{suffix}"
        target = models_dir / f"{approved_prefix}_{horizon}d{suffix}"
        shutil.copyfile(source, target)


if __name__ == "__main__":
    raise SystemExit(main())
