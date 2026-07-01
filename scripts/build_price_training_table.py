from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
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
        retail_series = _daily_retail_series(prices)
        at_wholesale_by_date = _daily_at_wholesale(prices)
        rows.extend(_training_rows(item_code, retail_series, at_wholesale_by_date, min_history=args.min_history))

    out_path = data_dir() / "model" / f"price_training_table_{target_date:%Y%m%d}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "base_date",
        "item_code",
        "avg_price",
        "price_pct_of_hist_mean",
        "lag_1_price",
        "lag_3_price",
        "lag_7_price",
        "lag_14_price",
        "ma_7_price",
        "ma_14_price",
        "ma_28_price",
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
        "at_wholesale_norm",
        "target_next_change",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {out_path.relative_to(REPO_ROOT)} rows={len(rows)}")
    if not rows:
        print("[WARN] No training rows produced; price history may be insufficient", file=sys.stderr)
    return 0


def _daily_retail_series(prices: list[Any]) -> list[tuple[date, float]]:
    """KAMIS national average retail price per date."""
    values_by_day: dict[date, list[float]] = defaultdict(list)
    for feature in prices:
        if feature.region_code not in (None, "평균"):
            continue
        price = feature.retail_price or feature.wholesale_price
        if price is None:
            continue
        values_by_day[feature.base_date].append(price)
    return sorted((day, mean(values)) for day, values in values_by_day.items() if values)


def _daily_at_wholesale(prices: list[Any]) -> dict[date, float]:
    """Average AT regional wholesale price per date (all regions)."""
    values_by_day: dict[date, list[float]] = defaultdict(list)
    for feature in prices:
        if feature.source not in ("at_regional_price", "at_market_settlement"):
            continue
        price = feature.wholesale_price or feature.settlement_price
        if price is None:
            continue
        values_by_day[feature.base_date].append(price)
    return {day: mean(vals) for day, vals in values_by_day.items() if vals}


def _training_rows(
    item_code: str,
    series: list[tuple[date, float]],
    at_wholesale_by_date: dict[date, float],
    min_history: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    min_required_history = max(min_history, 14)
    if len(series) <= min_required_history:
        return rows

    values = [value for _, value in series]
    hist_mean = mean(values) if values else 1.0

    for idx in range(min_required_history, len(series) - 1):
        base_date, current = series[idx]
        lag_1 = values[idx - 1]
        lag_3 = values[idx - 3]
        lag_7 = values[idx - 7]
        lag_14 = values[idx - 14]
        ma_7 = mean(values[max(0, idx - 7) : idx] or [current])
        ma_14 = mean(values[max(0, idx - 14) : idx] or [current])
        ma_28 = mean(values[max(0, idx - 28) : idx] or [current])
        returns_7 = _returns(values[idx - 7 : idx + 1])
        returns_14 = _returns(values[idx - 14 : idx + 1])
        next_value = values[idx + 1]

        # AT wholesale price normalized relative to KAMIS retail (wholesale/retail - 1)
        at_ws = at_wholesale_by_date.get(base_date)
        at_wholesale_norm = round(_pct_change(at_ws, current), 6) if at_ws and current else 0.0

        rows.append(
            {
                "base_date": base_date.isoformat(),
                "item_code": item_code,
                "avg_price": round(current, 4),
                "price_pct_of_hist_mean": round(_pct_change(current, hist_mean), 6),
                "lag_1_price": round(lag_1, 4),
                "lag_3_price": round(lag_3, 4),
                "lag_7_price": round(lag_7, 4),
                "lag_14_price": round(lag_14, 4),
                "ma_7_price": round(ma_7, 4),
                "ma_14_price": round(ma_14, 4),
                "ma_28_price": round(ma_28, 4),
                "change_1d": _pct_change(current, lag_1),
                "change_3d": _pct_change(current, lag_3),
                "change_7d": _pct_change(current, lag_7),
                "change_14d": _pct_change(current, lag_14),
                "ma_7_gap": _pct_change(current, ma_7),
                "ma_14_gap": _pct_change(current, ma_14),
                "volatility_7d": round(pstdev(returns_7), 6) if len(returns_7) > 1 else 0.0,
                "volatility_14d": round(pstdev(returns_14), 6) if len(returns_14) > 1 else 0.0,
                "weekday_sin": _cyclical_sin(base_date.weekday(), 7),
                "weekday_cos": _cyclical_cos(base_date.weekday(), 7),
                "month_sin": _cyclical_sin(base_date.month - 1, 12),
                "month_cos": _cyclical_cos(base_date.month - 1, 12),
                "at_wholesale_norm": at_wholesale_norm,
                "target_next_change": _pct_change(next_value, current),
            }
        )
    return rows


def _returns(values: list[float]) -> list[float]:
    return [_pct_change(values[idx], values[idx - 1]) for idx in range(1, len(values))]


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / previous, 6)


def _cyclical_sin(value: int, period: int) -> float:
    import math

    return round(math.sin(2 * math.pi * value / period), 6)


def _cyclical_cos(value: int, period: int) -> float:
    import math

    return round(math.cos(2 * math.pi * value / period), 6)


if __name__ == "__main__":
    sys.exit(main())
