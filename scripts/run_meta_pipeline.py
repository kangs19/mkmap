from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _report_dir_acc(report_path: Path) -> float | None:
    """평가 리포트에서 홀드아웃 방향정확도 읽기. 실패 시 None."""
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return float(data.get("overall", {}).get("direction_accuracy"))
    except Exception:
        return None


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
    training_ok = run_step(
        "Build price training table",
        [sys.executable, "scripts/build_price_training_table.py", "--date", args.date],
        soft_fail=True,
    )

    training_table = REPO_ROOT / "data" / "model" / f"price_training_table_{stamp}.csv"
    model_path = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}.json"
    model_report_path = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}_evaluation.json"
    prediction_path = REPO_ROOT / "data" / "model" / f"latest_price_predictions_{stamp}_risk.json"
    signal_path = REPO_ROOT / "data" / "signals" / stamp / "region_risk_signals.json"

    model_ok = training_ok and run_step(
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

    # ── 챔피언/챌린저: v2(물량·날씨·작물별 피처) 학습 후 홀드아웃 정확도가 더 높으면 채택 ──
    # 모든 단계 soft-fail + try/except → v2가 조금이라도 실패하면 v1 그대로 사용 (프로덕션 안전)
    try:
        v2_table = REPO_ROOT / "data" / "model" / f"price_training_table_{stamp}_v2.csv"
        v2_model = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}_v2.json"
        v2_report = REPO_ROOT / "data" / "model" / f"price_baseline_model_{stamp}_v2_evaluation.json"
        v2_build = run_step(
            "Build price training table v2 (물량·날씨·작물별 피처)",
            [sys.executable, "scripts/build_price_training_table_v2.py", "--date", args.date,
             "--output-suffix", "v2"],
            soft_fail=True,
        )
        v2_train = v2_build and run_step(
            "Train price model v2",
            [sys.executable, "scripts/train_price_baseline_model.py",
             "--input", str(v2_table), "--output", str(v2_model),
             "--report-output", str(v2_report)],
            soft_fail=True,
        )
        if v2_train and model_ok:
            acc_v1 = _report_dir_acc(model_report_path)
            acc_v2 = _report_dir_acc(v2_report)
            print(f"[champion/challenger] v1 dir_acc={acc_v1} vs v2 dir_acc={acc_v2}")
            adopted = "v1"
            reason = "v1 유지"
            if acc_v1 is not None and acc_v2 is not None:
                # 누수 의심 가드: v2 정확도가 비현실적으로 높거나(>0.9) 급등(>+0.15)이면 미채택
                suspicious = acc_v2 > 0.9 or (acc_v2 - acc_v1) > 0.15
                if suspicious:
                    reason = f"v2 의심(정확도 {acc_v2:.3f}, 급등) → v1 유지"
                elif acc_v2 >= acc_v1 + 0.005:
                    training_table = v2_table
                    model_path = v2_model
                    adopted = "v2"
                    reason = f"v2 채택 ({acc_v1:.3f}→{acc_v2:.3f})"
            print(f"[champion/challenger] {reason}")
            # 비교 결과 기록 (엔드포인트로 조회 가능)
            try:
                cmp_path = REPO_ROOT / "data" / "model" / "champion_challenger.json"
                cmp_path.write_text(json.dumps({
                    "date": args.date, "acc_v1": acc_v1, "acc_v2": acc_v2,
                    "adopted": adopted, "reason": reason,
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        print(f"[champion/challenger] 비교 실패, v1 유지: {exc}", file=sys.stderr)

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
