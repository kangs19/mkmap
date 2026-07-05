from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HORIZONS = (1, 7, 14, 30, 90, 180, 365)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train one price model per forecast horizon.")
    parser.add_argument("--input", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--horizons", default=",".join(str(day) for day in DEFAULT_HORIZONS))
    parser.add_argument("--min-rows", type=int, default=80)
    parser.add_argument("--backtest-min-train-rows", type=int, default=24)
    parser.add_argument("--backtest-window-count", type=int, default=8)
    parser.add_argument("--summary-output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "data" / "model" / "horizons"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or input_path.stem.replace("price_training_table_", "price_horizon_model_")
    horizons = _parse_horizons(args.horizons)
    availability = _target_availability(input_path)

    results = []
    for horizon in horizons:
        target_column = f"target_{horizon}d_change"
        usable_rows = availability.get(target_column, 0)
        if usable_rows < args.min_rows:
            results.append(
                {
                    "horizon_days": horizon,
                    "target_column": target_column,
                    "usable_rows": usable_rows,
                    "status": "skipped",
                    "reason": "not_enough_rows",
                    "min_rows": args.min_rows,
                }
            )
            continue

        model_path = output_dir / f"{prefix}_{horizon}d.json"
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "train_price_baseline_model.py"),
            "--input",
            str(input_path),
            "--target-column",
            target_column,
            "--output",
            str(model_path),
            "--backtest-min-train-rows",
            str(args.backtest_min_train_rows),
            "--backtest-window-count",
            str(args.backtest_window_count),
        ]
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        status = "trained" if completed.returncode == 0 else "failed"
        result = {
            "horizon_days": horizon,
            "target_column": target_column,
            "usable_rows": usable_rows,
            "status": status,
            "model_path": str(model_path) if completed.returncode == 0 else None,
        }
        if completed.returncode != 0:
            result["stderr"] = completed.stderr[-4000:]
            result["stdout"] = completed.stdout[-4000:]
        results.append(result)

    summary_path = Path(args.summary_output) if args.summary_output else output_dir / f"{prefix}_summary.json"
    summary = {
        "ok": all(result["status"] in {"trained", "skipped"} for result in results),
        "input": str(input_path),
        "availability": availability,
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


def _parse_horizons(raw: str) -> list[int]:
    horizons = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        horizons.append(int(part))
    return horizons


def _target_availability(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return counts
        target_columns = [field for field in reader.fieldnames if field.startswith("target_")]
        counts = {field: 0 for field in target_columns}
        for row in reader:
            for field in target_columns:
                value = row.get(field)
                if value not in (None, ""):
                    counts[field] += 1
    return counts


if __name__ == "__main__":
    sys.exit(main())
