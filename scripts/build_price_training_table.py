from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.cached import CachedPriceConnector
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build item-level price time-series training rows.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Feature cache date, YYYY-MM-DD")
    parser.add_argument("--min-history", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    registry = default_registry()
    connector = CachedPriceConnector()
    rows: list[dict[str, Any]] = []

    for item_code in sorted(registry.all_items()):
        prices = connector.fetch_prices(item_code, target_date)
        series = _daily_average_series(prices)
        rows.extend(_training_rows(item_code, series, min_history=args.min_history))

    out_path = data_dir() / "model" / f"price_training_table_{target_date:%Y%m%d}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "base_date",
        "item_code",
        "avg_price",
        "lag_1_price",
        "lag_3_price",
        "ma_7_price",
        "change_1d",
        "change_3d",
        "target_next_change",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {out_path.relative_to(REPO_ROOT)} rows={len(rows)}")
    return 0 if rows else 1


def _daily_average_series(prices: list[Any]) -> list[tuple[date, float]]:
    values_by_day: dict[date, list[float]] = defaultdict(list)
    for feature in prices:
        if feature.region_code not in (None, "평균"):
            continue
        price = feature.retail_price or feature.wholesale_price
        if price is None:
            continue
        values_by_day[feature.base_date].append(price)

    return sorted((day, mean(values)) for day, values in values_by_day.items() if values)


def _training_rows(item_code: str, series: list[tuple[date, float]], min_history: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if len(series) <= min_history:
        return rows

    values = [value for _, value in series]
    for idx in range(min_history, len(series) - 1):
        base_date, current = series[idx]
        lag_1 = values[idx - 1]
        lag_3 = values[idx - 3]
        ma_7 = mean(values[idx - 7 : idx])
        next_value = values[idx + 1]
        rows.append(
            {
                "base_date": base_date.isoformat(),
                "item_code": item_code,
                "avg_price": round(current, 4),
                "lag_1_price": round(lag_1, 4),
                "lag_3_price": round(lag_3, 4),
                "ma_7_price": round(ma_7, 4),
                "change_1d": _pct_change(current, lag_1),
                "change_3d": _pct_change(current, lag_3),
                "target_next_change": _pct_change(next_value, current),
            }
        )
    return rows


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / previous, 6)


if __name__ == "__main__":
    sys.exit(main())
