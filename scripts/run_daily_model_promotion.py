from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_HORIZONS = (1, 14, 30, 90, 180, 365)

COMPACT_90D_FEATURES = (
    "price_pct_of_hist_mean",
    "change_1d",
    "change_3d",
    "change_7d",
    "change_14d",
    "ma_7_gap",
    "ma_14_gap",
    "volatility_7d",
    "volatility_14d",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
    "agromarket_wholesale_norm",
    "agromarket_settlement_norm",
    "agromarket_volume_norm",
    "agromarket_auction_norm",
    "agromarket_auction_volume_norm",
    "agromarket_auction_dominant_share",
    "agromarket_auction_seasonal_share",
    "agromarket_auction_stored_share",
    "agromarket_auction_processed_share",
    "agromarket_auction_imported_share",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily train, compare, and publish approved price horizon models.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Feature/model date, YYYY-MM-DD")
    parser.add_argument("--baseline-prefix", required=True, help="Current approved model prefix")
    parser.add_argument("--candidate-prefix", default=None, help="Candidate prefix. Defaults to daily_candidate_YYYYMMDD")
    parser.add_argument("--approved-prefix", default=None, help="Approved output prefix. Defaults to daily_approved_YYYYMMDD")
    parser.add_argument("--horizons", default="1,14,30,90,180,365")
    parser.add_argument("--backtest-window-count", type=int, default=40)
    parser.add_argument("--backtest-min-train-rows", type=int, default=120)
    parser.add_argument("--robustness-samples-per-era", type=int, default=5)
    parser.add_argument("--min-history", type=int, default=14)
    parser.add_argument("--skip-train", action="store_true", help="Use existing candidate artifacts.")
    parser.add_argument("--skip-robustness", action="store_true", help="Skip temporal robustness reports.")
    parser.add_argument("--output", default=None, help="Run summary JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_date = date.fromisoformat(args.date)
    date_tag = run_date.strftime("%Y%m%d")
    horizons = _parse_horizons(args.horizons)
    candidate_prefix = args.candidate_prefix or f"price_horizon_model_{date_tag}_daily_candidate"
    approved_prefix = args.approved_prefix or f"price_horizon_model_{date_tag}_daily_approved"
    models_dir = REPO_ROOT / "data" / "model" / "horizons"
    feature_path = REPO_ROOT / "data" / "model" / f"price_training_table_{date_tag}.csv"

    steps: list[dict[str, Any]] = []
    ok = True

    if not args.skip_train:
        ok &= _run_step(
            steps,
            "build_training_table",
            [
                sys.executable,
                "scripts/build_price_training_table.py",
                "--date",
                args.date,
                "--min-history",
                str(args.min_history),
            ],
        )
        for horizon in horizons:
            command = [
                sys.executable,
                "scripts/train_price_baseline_model.py",
                "--input",
                str(feature_path),
                "--target-column",
                f"target_{horizon}d_change",
                "--output",
                str(models_dir / f"{candidate_prefix}_{horizon}d.json"),
                "--backtest-min-train-rows",
                str(args.backtest_min_train_rows),
                "--backtest-window-count",
                str(args.backtest_window_count),
            ]
            if horizon == 90:
                command.extend(["--include-features", ",".join(COMPACT_90D_FEATURES)])
            ok &= _run_step(steps, f"train_{horizon}d_candidate", command)

    ok &= _run_step(
        steps,
        "build_mixed_approved",
        [
            sys.executable,
            "scripts/build_mixed_horizon_model_set.py",
            "--models-dir",
            str(models_dir),
            "--baseline-prefix",
            args.baseline_prefix,
            "--candidate-prefix",
            candidate_prefix,
            "--approved-prefix",
            approved_prefix,
            "--horizons",
            ",".join(str(horizon) for horizon in horizons),
            "--output",
            str(models_dir / f"{approved_prefix}_approval_report.json"),
        ],
    )

    quality_path = models_dir / f"{approved_prefix}_quality.json"
    ok &= _run_step(
        steps,
        "quality_standard",
        [
            sys.executable,
            "scripts/audit_price_horizon_quality.py",
            "--models-dir",
            str(models_dir),
            "--model-prefix",
            approved_prefix,
            "--output",
            str(quality_path),
        ],
    )

    warn_quality_path = None
    hold_quality_path = None
    if not args.skip_robustness:
        robustness_path = models_dir / f"{approved_prefix}_robustness.json"
        ok &= _run_step(
            steps,
            "robustness",
            [
                sys.executable,
                "scripts/audit_price_model_robustness.py",
                "--features",
                str(feature_path),
                "--models-dir",
                str(models_dir),
                "--model-prefix",
                approved_prefix,
                "--horizons",
                ",".join(str(horizon) for horizon in horizons),
                "--samples-per-era",
                str(args.robustness_samples_per_era),
                "--output",
                str(robustness_path),
            ],
        )
        warn_quality_path = models_dir / f"{approved_prefix}_quality_temporal_warn.json"
        hold_quality_path = models_dir / f"{approved_prefix}_quality_temporal_hold.json"
        ok &= _run_step(
            steps,
            "quality_temporal_warn",
            _quality_command(models_dir, approved_prefix, robustness_path, warn_quality_path, "warn"),
        )
        _run_step(
            steps,
            "quality_temporal_hold",
            _quality_command(models_dir, approved_prefix, robustness_path, hold_quality_path, "hold"),
            allow_exit_codes={0, 1},
        )

    prediction_quality_path = warn_quality_path or quality_path
    strict_quality_path = hold_quality_path or quality_path
    warn_predictions = REPO_ROOT / "data" / "model" / f"latest_price_horizon_predictions_{date_tag}_daily_warn_candidates.json"
    strict_predictions = REPO_ROOT / "data" / "model" / f"latest_price_horizon_predictions_{date_tag}_daily_strict_candidates.json"
    warn_explanations = REPO_ROOT / "data" / "model" / f"latest_price_horizon_explanations_{date_tag}_daily_warn_candidates.json"
    strict_explanations = REPO_ROOT / "data" / "model" / f"latest_price_horizon_explanations_{date_tag}_daily_strict_candidates.json"

    ok &= _run_step(
        steps,
        "predict_warn",
        _predict_command(feature_path, models_dir, approved_prefix, prediction_quality_path, horizons, warn_predictions),
    )
    ok &= _run_step(
        steps,
        "predict_strict",
        _predict_command(feature_path, models_dir, approved_prefix, strict_quality_path, horizons, strict_predictions),
    )
    ok &= _run_step(
        steps,
        "explain_warn",
        _explain_command(feature_path, models_dir, approved_prefix, warn_predictions, prediction_quality_path, warn_explanations),
    )
    ok &= _run_step(
        steps,
        "explain_strict",
        _explain_command(feature_path, models_dir, approved_prefix, strict_predictions, strict_quality_path, strict_explanations),
    )

    payload = {
        "ok": bool(ok),
        "date": args.date,
        "baseline_prefix": args.baseline_prefix,
        "candidate_prefix": candidate_prefix,
        "approved_prefix": approved_prefix,
        "horizons": horizons,
        "steps": steps,
        "artifacts": {
            "feature_table": str(feature_path),
            "models_dir": str(models_dir),
            "quality": str(quality_path),
            "warn_predictions": str(warn_predictions),
            "strict_predictions": str(strict_predictions),
            "warn_explanations": str(warn_explanations),
            "strict_explanations": str(strict_explanations),
        },
    }
    output_path = Path(args.output) if args.output else REPO_ROOT / "data" / "model" / f"daily_model_promotion_{date_tag}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**payload, "output": str(output_path)}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def _parse_horizons(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _run_step(
    steps: list[dict[str, Any]],
    name: str,
    command: list[str],
    allow_exit_codes: set[int] | None = None,
) -> bool:
    allow_exit_codes = allow_exit_codes or {0}
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
    step = {
        "name": name,
        "exit_code": completed.returncode,
        "ok": completed.returncode in allow_exit_codes,
        "command": command,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    steps.append(step)
    print(json.dumps({"step": name, "ok": step["ok"], "exit_code": completed.returncode}, ensure_ascii=False))
    return bool(step["ok"])


def _quality_command(models_dir: Path, prefix: str, robustness_path: Path, output: Path, policy: str) -> list[str]:
    return [
        sys.executable,
        "scripts/audit_price_horizon_quality.py",
        "--models-dir",
        str(models_dir),
        "--model-prefix",
        prefix,
        "--robustness-report",
        str(robustness_path),
        "--temporal-policy",
        policy,
        "--output",
        str(output),
    ]


def _predict_command(
    features: Path,
    models_dir: Path,
    prefix: str,
    quality_path: Path,
    horizons: list[int],
    output: Path,
) -> list[str]:
    return [
        sys.executable,
        "scripts/predict_price_horizons.py",
        "--features",
        str(features),
        "--models-dir",
        str(models_dir),
        "--model-prefix",
        prefix,
        "--quality-report",
        str(quality_path),
        "--only-candidates",
        "--horizons",
        ",".join(str(horizon) for horizon in horizons),
        "--output",
        str(output),
    ]


def _explain_command(
    features: Path,
    models_dir: Path,
    prefix: str,
    predictions: Path,
    quality_path: Path,
    output: Path,
) -> list[str]:
    return [
        sys.executable,
        "scripts/explain_price_horizon_predictions.py",
        "--features",
        str(features),
        "--models-dir",
        str(models_dir),
        "--model-prefix",
        prefix,
        "--predictions",
        str(predictions),
        "--quality-report",
        str(quality_path),
        "--output",
        str(output),
    ]


if __name__ == "__main__":
    sys.exit(main())
