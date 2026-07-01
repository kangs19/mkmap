from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

FAST_CHECKS = [
    ("metadata validation", ["scripts/validate_metadata.py"]),
    ("external mapping validation", ["scripts/validate_external_mappings.py"]),
    ("text encoding health", ["scripts/check_text_encoding_health.py"]),
    ("API service catalog smoke", ["scripts/smoke_api_services.py"]),
    ("price model smoke", ["scripts/smoke_price_model_pipeline.py"]),
    ("forecast scope contract smoke", ["scripts/smoke_forecast_scope_contract.py"]),
]

SLOW_CHECKS = [
    ("API contract smoke", ["scripts/smoke_api_contract.py"]),
    ("risk signal smoke", ["scripts/smoke_risk_signal.py"]),
]

PY_COMPILE_TARGETS = [
    "scripts/run_meta_pipeline.py",
    "scripts/collect_live_event_features.py",
    "scripts/collect_live_price_features.py",
    "scripts/collect_live_weather_features.py",
    "scripts/import_meta_outputs_to_backend.py",
    "scripts/build_price_training_table.py",
    "scripts/train_price_baseline_model.py",
    "scripts/predict_latest_prices.py",
    "scripts/run_live_api_diagnostics.py",
    "scripts/verify_public_api_outputs.py",
    "scripts/test_live_at_market_settlement.py",
    "scripts/test_live_at_regional_price.py",
    "scripts/test_live_impact_forecast.py",
    "scripts/test_live_rda_agri_weather.py",
    "scripts/test_live_satellite.py",
    "scripts/test_live_weather_chart.py",
    "scripts/run_smoke_suite.py",
    "backend/app/main.py",
    "backend/app/routers/admin.py",
    "backend/app/routers/forecasts.py",
    "backend/app/routers/signals.py",
    "backend/app/scheduler.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local non-secret MK Map smoke checks.")
    parser.add_argument("--skip-py-compile", action="store_true")
    parser.add_argument("--include-slow", action="store_true", help="Also run slower API contract and risk signal checks.")
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []

    if not args.skip_py_compile:
        if not _run("py_compile", ["-m", "py_compile", *PY_COMPILE_TARGETS], args.timeout_seconds):
            failures.append("py_compile")

    checks = [*FAST_CHECKS]
    if args.include_slow:
        checks.extend(SLOW_CHECKS)

    for name, command in checks:
        if not _run(name, command, args.timeout_seconds):
            failures.append(name)

    if failures:
        print("\nSmoke suite failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nSmoke suite passed.")
    if not args.include_slow:
        print("Slow checks skipped. Re-run with --include-slow to include API contract and risk signal checks.")
    return 0


def _run(name: str, command: list[str], timeout_seconds: int) -> bool:
    print(f"\n== {name} ==")
    full_command = [sys.executable, *command]
    print(" ".join(full_command))
    sys.stdout.flush()
    try:
        result = subprocess.run(full_command, cwd=REPO_ROOT, timeout=timeout_seconds)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"{name} timed out after {timeout_seconds}s")
        return False


if __name__ == "__main__":
    sys.exit(main())
