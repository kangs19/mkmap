from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        training_path = tmp_path / "training.csv"
        model_path = tmp_path / "model.json"
        report_path = tmp_path / "model_evaluation.json"
        prediction_path = tmp_path / "predictions.json"

        _write_training_csv(training_path)

        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "train_price_baseline_model.py"),
                "--input",
                str(training_path),
                "--output",
                str(model_path),
                "--report-output",
                str(report_path),
            ],
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "predict_latest_prices.py"),
                "--features",
                str(training_path),
                "--model",
                str(model_path),
                "--output",
                str(prediction_path),
            ],
            check=True,
            cwd=REPO_ROOT,
        )

        model = json.loads(model_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        predictions = json.loads(prediction_path.read_text(encoding="utf-8"))

        assert model["model_type"] == "standardized_linear_baseline"
        assert len(model["features"]) >= 4
        assert "direction_threshold" in model
        assert "by_item" in report
        assert len(predictions) == 2
        assert all("direction_threshold" in row for row in predictions)
        assert all("risk_adjusted_next_change" in row for row in predictions)

    print("Price model pipeline smoke test passed")
    return 0


def _write_training_csv(path: Path) -> None:
    fieldnames = [
        "base_date",
        "item_code",
        "avg_price",
        "lag_1_price",
        "lag_3_price",
        "ma_7_price",
        "change_1d",
        "change_3d",
        "ma_7_gap",
        "volatility_7d",
        "target_next_change",
    ]
    start = date(2026, 1, 1)
    rows = []
    for idx in range(40):
        for item_offset, item_code in enumerate(["cabbage", "radish"]):
            trend = 1 + idx * (0.003 + item_offset * 0.001)
            price = 1000 * (item_offset + 1) * trend
            lag_1 = price / (1.003 + item_offset * 0.001)
            lag_3 = price / (1.009 + item_offset * 0.003)
            ma_7 = price / (1.006 + item_offset * 0.002)
            target = 0.003 + item_offset * 0.001
            rows.append(
                {
                    "base_date": (start + timedelta(days=idx)).isoformat(),
                    "item_code": item_code,
                    "avg_price": round(price, 4),
                    "lag_1_price": round(lag_1, 4),
                    "lag_3_price": round(lag_3, 4),
                    "ma_7_price": round(ma_7, 4),
                    "change_1d": round((price - lag_1) / lag_1, 6),
                    "change_3d": round((price - lag_3) / lag_3, 6),
                    "ma_7_gap": round((price - ma_7) / ma_7, 6),
                    "volatility_7d": round(0.01 + idx * 0.0001, 6),
                    "target_next_change": target,
                }
            )

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    sys.exit(main())
