from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the mkmap_meta daily pipeline end to end.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--year", type=int, default=None, help="KOSIS production target year. Defaults to date year.")
    parser.add_argument("--price-days-back", type=int, default=365)
    parser.add_argument("--weather-lookback-days", type=int, default=0)
    parser.add_argument("--weather-max-requests-per-item", type=int, default=16)
    parser.add_argument("--weather-request-timeout-seconds", type=int, default=8)
    parser.add_argument("--skip-collect", action="store_true", help="Reuse existing data/features cache files.")
    parser.add_argument("--skip-weather", action="store_true", help="Skip KMA crop weather collection.")
    parser.add_argument("--skip-backend-import", action="store_true", help="Do not import outputs into backend DB.")
    return parser.parse_args()


def run_step(name: str, args: list[str], soft_fail: bool = False) -> bool:
    """Run a pipeline step. Returns True on success, False on failure.
    If soft_fail=True, logs a warning on non-zero exit instead of raising.
    """
    print(f"\n== {name} ==")
    print(" ".join(args))
    result = subprocess.run(args, cwd=REPO_ROOT)
    if result.returncode != 0:
        if soft_fail:
            print(f"[WARN] {name} exited with code {result.returncode}; continuing", file=sys.stderr)
            return False
        raise subprocess.CalledProcessError(result.returncode, args)
    return True


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    year = args.year or target_date.year
    stamp = f"{target_date:%Y%m%d}"

    if not args.skip_collect:
        run_step(
            "Collect KAMIS prices",
            [sys.executable, "scripts/collect_live_price_features.py", "--date", args.date, "--days-back", str(args.price_days_back)],
        )
        run_step(
            "Collect KOSIS production",
            [sys.executable, "scripts/collect_live_production_features.py", "--date", args.date, "--year", str(year)],
        )
        run_step(
            "Collect KMA events",
            [sys.executable, "scripts/collect_live_event_features.py", "--date", args.date],
        )
        if not args.skip_weather:
            run_step(
                "Collect KMA crop weather",
                [
                    sys.executable,
                    "scripts/collect_live_weather_features.py",
                    "--date",
                    args.date,
                    "--lookback-days",
                    str(args.weather_lookback_days),
                    "--max-requests-per-item",
                    str(args.weather_max_requests_per_item),
                    "--request-timeout-seconds",
                    str(args.weather_request_timeout_seconds),
                ],
                soft_fail=True,
            )

    run_step("Build region-risk model dataset", [sys.executable, "scripts/build_model_dataset.py", "--date", args.date])
    run_step("Export live risk signals", [sys.executable, "scripts/export_live_signals.py", "--date", args.date])
    run_step(
        "Export DB prices to cache",
        [sys.executable, "scripts/export_db_prices_to_cache.py", "--date", args.date, "--days-back", "90"],
        soft_fail=True,
    )
    run_step("Build price training table", [sys.executable, "scripts/build_price_training_table.py", "--date", args.date])

    training_table = REPO_ROOT / "data" / "model" / f"price_training_table_{stamp}.csv"
    model_path = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}.json"
    model_report_path = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}_evaluation.json"
    prediction_path = REPO_ROOT / "data" / "model" / f"latest_price_predictions_{stamp}_risk.json"
    signal_path = REPO_ROOT / "data" / "signals" / stamp / "region_risk_signals.json"

    model_ok = run_step(
        "Train baseline price model",
        [
            sys.executable,
            "scripts/train_price_baseline_model.py",
            "--input",
            str(training_table),
            "--output",
            str(model_path),
            "--report-output",
            str(model_report_path),
        ],
        soft_fail=True,
    )
    if model_ok:
        run_step(
            "Predict latest prices with risk overlay",
            [
                sys.executable,
                "scripts/predict_latest_prices.py",
                "--features",
                str(training_table),
                "--model",
                str(model_path),
                "--signals",
                str(signal_path),
                "--output",
                str(prediction_path),
            ],
            soft_fail=True,
        )
    else:
        print("[WARN] Skipping price prediction: model training failed", file=sys.stderr)

    if not args.skip_backend_import:
        run_step("Import outputs into backend DB", [sys.executable, "scripts/import_meta_outputs_to_backend.py", "--date", args.date])

    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
