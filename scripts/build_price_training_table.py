from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.cached import CachedPriceConnector
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import data_dir, read_json
from scripts.farmmap_capacity_features import (
    FARMMAP_FEATURE_COLUMNS,
    default_farmmap_capacity_features,
    load_farmmap_capacity_features_by_item,
)


TARGET_HORIZONS_DAYS = (1, 7, 14, 30, 90, 180, 365)

ITEM_SPECIFIC_FEATURES = [
    "cabbage_kimjang_urgency_30d",
    "cabbage_kimjang_urgency_90d",
    "cabbage_season_phase",
    "cabbage_highland_temp_stress",
    "cabbage_autumn_supply_pressure",
    "cabbage_kimjang_vol_spike",
    "radish_kimjang_demand",
    "radish_summer_heat_loss_risk",
    "radish_winter_phase",
    "radish_spring_glut",
    "onion_storage_depletion_idx",
    "onion_harvest_proximity_60d",
    "onion_storage_scarcity_risk",
    "garlic_storage_month_idx",
    "garlic_scarcity_risk",
    "garlic_winter_cold_damage",
    "garlic_harvest_pressure",
    "garlic_post_harvest_down_pressure",
    "green_onion_heat_stress",
    "green_onion_cold_damage",
    "green_onion_heavy_rain",
    "green_onion_supply_disruption",
    "green_onion_summer_down_pressure",
    "green_onion_late_june_normalization",
    "radish_summer_glut_pressure",
    "radish_august_14d_down_pressure",
    "onion_post_harvest_supply_pressure",
    "onion_autumn_storage_transition",
    "onion_june_rebound_14d",
    "onion_autumn_14d_correction",
    "cabbage_spring_supply_pressure",
    "cabbage_may_long_down_pressure",
    "cabbage_early_autumn_14d_correction",
    "garlic_june_post_harvest_softening_14d",
    "green_onion_august_14d_down_pressure",
]


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
    supply_by_month = _monthly_supply_context_features()
    farmmap_features_by_item = load_farmmap_capacity_features_by_item()

    for item_code in sorted(registry.all_items()):
        prices = connector.fetch_prices(item_code, target_date)
        retail_series, agromarket_scale = _daily_target_retail_series(prices)
        at_wholesale_by_date = _daily_at_wholesale(prices)
        agromarket_by_date = _daily_agromarket_features(prices, agromarket_scale=agromarket_scale)
        weather_by_date = _daily_weather_features(item_code)
        rows.extend(
            _training_rows(
                item_code,
                retail_series,
                at_wholesale_by_date,
                agromarket_by_date,
                weather_by_date,
                supply_by_month,
                farmmap_features_by_item.get(item_code, default_farmmap_capacity_features()),
                min_history=args.min_history,
            )
        )

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
        "agromarket_wholesale_norm",
        "agromarket_retail_norm",
        "agromarket_settlement_norm",
        "agromarket_volume_norm",
        "agromarket_auction_norm",
        "agromarket_auction_volume_norm",
        "agromarket_auction_dominant_share",
        "agromarket_auction_seasonal_share",
        "agromarket_auction_stored_share",
        "agromarket_auction_processed_share",
        "agromarket_auction_imported_share",
        "weather_temp_norm",
        "weather_rainfall_norm",
        "weather_humidity_norm",
        "weather_sunshine_norm",
        "weather_obs_norm",
        "supply_rain_reservoir_risk",
        "supply_weather_alert_insurance_risk",
        *FARMMAP_FEATURE_COLUMNS,
        *ITEM_SPECIFIC_FEATURES,
        "target_next_change",
        *[f"target_{days}d_change" for days in TARGET_HORIZONS_DAYS],
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {out_path.relative_to(REPO_ROOT)} rows={len(rows)}")
    if not rows:
        print("[WARN] No training rows produced; price history may be insufficient", file=sys.stderr)
        return 1
    return 0


def _daily_target_retail_series(prices: list[Any]) -> tuple[list[tuple[date, float]], float]:
    """Daily target series. Prefer KAMIS, then fill missing days with AgroMarket retail."""
    kamis_by_day: dict[date, list[float]] = defaultdict(list)
    agromarket_by_day: dict[date, list[float]] = defaultdict(list)
    for feature in prices:
        if feature.source in ("kamis", "kamis_price"):
            if feature.region_code not in (None, "평균", "?됯퇏"):
                continue
            price = feature.retail_price or feature.wholesale_price
            if price is not None:
                kamis_by_day[feature.base_date].append(price)
        elif feature.source == "agromarket_retail_price" and feature.retail_price is not None:
            agromarket_by_day[feature.base_date].append(feature.retail_price)

    agromarket_scale = _overlap_scale(kamis_by_day, agromarket_by_day)
    series = []
    for day in sorted(set(kamis_by_day) | set(agromarket_by_day)):
        if kamis_by_day.get(day):
            values = kamis_by_day[day]
            series.append((day, mean(values)))
        elif agromarket_by_day.get(day):
            series.append((day, mean(agromarket_by_day[day]) * agromarket_scale))
    return series, agromarket_scale


def _overlap_scale(primary_by_day: dict[date, list[float]], fallback_by_day: dict[date, list[float]]) -> float:
    ratios = []
    for day in sorted(set(primary_by_day) & set(fallback_by_day)):
        primary = mean(primary_by_day[day])
        fallback = mean(fallback_by_day[day])
        if primary > 0 and fallback > 0:
            ratios.append(primary / fallback)
    if not ratios:
        return 1.0
    return median(ratios)


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


def _daily_agromarket_features(prices: list[Any], agromarket_scale: float = 1.0) -> dict[date, dict[str, float]]:
    values: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for feature in prices:
        if feature.source == "agromarket_wholesale_price" and feature.wholesale_price is not None:
            values[feature.base_date]["wholesale"].append(feature.wholesale_price)
        elif feature.source == "agromarket_retail_price" and feature.retail_price is not None:
            values[feature.base_date]["retail"].append(feature.retail_price * agromarket_scale)
        elif feature.source == "agromarket_settlement":
            if feature.settlement_price is not None:
                values[feature.base_date]["settlement"].append(feature.settlement_price)
            if feature.volume is not None:
                values[feature.base_date]["volume"].append(feature.volume)
        elif feature.source == "agromarket_auction_price":
            if feature.wholesale_price is not None:
                values[feature.base_date]["auction"].append(feature.wholesale_price)
            if feature.volume is not None:
                values[feature.base_date]["auction_volume"].append(feature.volume)
            raw = feature.raw if isinstance(feature.raw, dict) else {}
            for key, value in _auction_variant_share_features(raw).items():
                values[feature.base_date][key].append(value)

    return {
        day: {name: mean(vals) for name, vals in grouped.items() if vals}
        for day, grouped in values.items()
    }


def _daily_weather_features(item_code: str) -> dict[date, dict[str, float]]:
    values: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    base = data_dir() / "features"
    if not base.exists():
        return {}

    for source_name in ("kma_crop_weather", "rda_agri_weather"):
        for path in base.glob(f"*/{source_name}_{item_code}.json"):
            rows = _safe_read_list(path)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                base_date = _parse_date(row.get("base_date"))
                if base_date is None:
                    continue
                _append_float(values[base_date]["temperature"], row.get("temperature"))
                _append_float(values[base_date]["rainfall"], row.get("rainfall"))
                _append_float(values[base_date]["humidity"], row.get("humidity"))
                _append_float(values[base_date]["sunshine"], row.get("sunshine"))
                values[base_date]["obs_count"].append(1.0)

    return {
        day: {
            "temperature": mean(grouped["temperature"]) if grouped.get("temperature") else 0.0,
            "rainfall": sum(grouped["rainfall"]) if grouped.get("rainfall") else 0.0,
            "humidity": mean(grouped["humidity"]) if grouped.get("humidity") else 0.0,
            "sunshine": mean(grouped["sunshine"]) if grouped.get("sunshine") else 0.0,
            "obs_count": sum(grouped["obs_count"]) if grouped.get("obs_count") else 0.0,
        }
        for day, grouped in values.items()
    }


def _monthly_supply_context_features() -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    base = data_dir() / "features"
    if not base.exists():
        return {}

    for source_name, key in (
        ("rain_reservoir", "rain_reservoir_risk"),
        ("weather_alert_insurance", "weather_alert_insurance_risk"),
    ):
        for path in base.glob(f"*/{source_name}.json"):
            rows = _safe_read_list(path)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                base_date = _parse_date(row.get("base_date"))
                if base_date is None:
                    continue
                value = _optional_float(row.get("severity_score"))
                if value is not None:
                    values[f"{base_date:%Y-%m}"][key].append(value)

    return {
        month: {name: mean(grouped_values) for name, grouped_values in grouped.items() if grouped_values}
        for month, grouped in values.items()
    }


def _training_rows(
    item_code: str,
    series: list[tuple[date, float]],
    at_wholesale_by_date: dict[date, float],
    agromarket_by_date: dict[date, dict[str, float]],
    weather_by_date: dict[date, dict[str, float]],
    supply_by_month: dict[str, dict[str, float]],
    farmmap_features: dict[str, float],
    min_history: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    min_required_history = max(min_history, 14)
    # lag_14 접근(idx=14) + target_next_change(idx+1) = 최소 16행 필요
    if len(series) < min_required_history + 2:
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
        horizon_targets = _horizon_targets(series, idx, current)

        # AT wholesale price normalized relative to KAMIS retail (wholesale/retail - 1)
        at_ws = at_wholesale_by_date.get(base_date)
        at_wholesale_norm = round(_pct_change(at_ws, current), 6) if at_ws and current else 0.0
        agromarket = agromarket_by_date.get(base_date, {})
        ag_wholesale_norm = round(_pct_change(agromarket.get("wholesale"), current), 6) if agromarket.get("wholesale") and current else 0.0
        ag_retail_norm = round(_pct_change(agromarket.get("retail"), current), 6) if agromarket.get("retail") and current else 0.0
        ag_settlement_norm = round(_pct_change(agromarket.get("settlement"), current), 6) if agromarket.get("settlement") and current else 0.0
        ag_volume_norm = _safe_log_norm(agromarket.get("volume"))
        ag_auction_norm = round(_pct_change(agromarket.get("auction"), current), 6) if agromarket.get("auction") and current else 0.0
        ag_auction_volume_norm = _safe_log_norm(agromarket.get("auction_volume"))
        weather = weather_by_date.get(base_date, {})
        supply = supply_by_month.get(f"{base_date:%Y-%m}", {})
        item_specific = _item_specific_features(
            item_code=item_code,
            base_date=base_date,
            weather=weather,
            supply=supply,
            volatility_14d=round(pstdev(returns_14), 6) if len(returns_14) > 1 else 0.0,
            ag_volume_norm=ag_volume_norm,
        )
        farmmap_row = {
            column: round(float(farmmap_features.get(column, 0.0)), 6)
            for column in FARMMAP_FEATURE_COLUMNS
        }

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
                "agromarket_wholesale_norm": ag_wholesale_norm,
                "agromarket_retail_norm": ag_retail_norm,
                "agromarket_settlement_norm": ag_settlement_norm,
                "agromarket_volume_norm": ag_volume_norm,
                "agromarket_auction_norm": ag_auction_norm,
                "agromarket_auction_volume_norm": ag_auction_volume_norm,
                "agromarket_auction_dominant_share": round(agromarket.get("auction_dominant_share", 0.0), 6),
                "agromarket_auction_seasonal_share": round(agromarket.get("auction_seasonal_share", 0.0), 6),
                "agromarket_auction_stored_share": round(agromarket.get("auction_stored_share", 0.0), 6),
                "agromarket_auction_processed_share": round(agromarket.get("auction_processed_share", 0.0), 6),
                "agromarket_auction_imported_share": round(agromarket.get("auction_imported_share", 0.0), 6),
                "weather_temp_norm": round(float(weather.get("temperature", 0.0)) / 40.0, 6),
                "weather_rainfall_norm": _safe_log_norm(float(weather.get("rainfall", 0.0))),
                "weather_humidity_norm": round(float(weather.get("humidity", 0.0)) / 100.0, 6),
                "weather_sunshine_norm": round(float(weather.get("sunshine", 0.0)) / 30.0, 6),
                "weather_obs_norm": round(min(float(weather.get("obs_count", 0.0)), 100.0) / 100.0, 6),
                "supply_rain_reservoir_risk": round(float(supply.get("rain_reservoir_risk", 0.0)), 6),
                "supply_weather_alert_insurance_risk": round(float(supply.get("weather_alert_insurance_risk", 0.0)), 6),
                **farmmap_row,
                **item_specific,
                "target_next_change": _pct_change(next_value, current),
                **horizon_targets,
            }
        )
    return rows


def _horizon_targets(series: list[tuple[date, float]], idx: int, current: float) -> dict[str, float | None]:
    base_date = series[idx][0]
    targets: dict[str, float | None] = {}
    for days in TARGET_HORIZONS_DAYS:
        future_value = _future_value_on_or_after(series, idx, base_date + timedelta(days=days))
        targets[f"target_{days}d_change"] = _pct_change(future_value, current) if future_value is not None else None
    return targets


def _item_specific_features(
    *,
    item_code: str,
    base_date: date,
    weather: dict[str, float],
    supply: dict[str, float],
    volatility_14d: float,
    ag_volume_norm: float,
) -> dict[str, float]:
    features = {name: 0.0 for name in ITEM_SPECIFIC_FEATURES}
    month = base_date.month
    temp = float(weather.get("temperature", 0.0))
    rainfall = float(weather.get("rainfall", 0.0))
    supply_alert = float(supply.get("weather_alert_insurance_risk", 0.0))

    if item_code == "cabbage":
        kimjang_30 = _event_proximity(base_date, 11, 20, 30)
        kimjang_90 = _event_proximity(base_date, 11, 20, 90)
        season_phase = _cabbage_phase(month)
        spring_supply = 1.0 if month == 5 else 0.7 if month == 6 else 0.0
        features.update(
            {
                "cabbage_kimjang_urgency_30d": kimjang_30,
                "cabbage_kimjang_urgency_90d": kimjang_90,
                "cabbage_season_phase": season_phase / 3.0,
                "cabbage_highland_temp_stress": _positive(temp - 26.0) / 15.0 if season_phase == 1 else 0.0,
                "cabbage_autumn_supply_pressure": ag_volume_norm if season_phase == 2 else 0.0,
                "cabbage_kimjang_vol_spike": volatility_14d * (kimjang_30 + kimjang_90) / 2.0,
                "cabbage_spring_supply_pressure": spring_supply,
                "cabbage_may_long_down_pressure": 1.0 if month == 5 else 0.0,
                "cabbage_early_autumn_14d_correction": 1.0 if month in {9, 10} else 0.0,
            }
        )
    elif item_code == "radish":
        kimjang = _event_proximity(base_date, 11, 20, 75)
        summer_glut = 1.0 if month in {7, 8} else 0.4 if month == 6 else 0.0
        features.update(
            {
                "radish_kimjang_demand": kimjang,
                "radish_summer_heat_loss_risk": _positive(temp - 28.0) / 15.0 if month in {7, 8} else 0.0,
                "radish_winter_phase": 1.0 if month in {12, 1, 2} else 0.0,
                "radish_spring_glut": 0.7 if month == 4 else 1.0 if month == 5 else 0.0,
                "radish_summer_glut_pressure": summer_glut,
                "radish_august_14d_down_pressure": 1.0 if month == 8 else 0.5 if month == 7 else 0.0,
            }
        )
    elif item_code == "onion":
        depletion = _onion_storage_depletion(month)
        harvest_proximity = _event_proximity(base_date, 5, 1, 60)
        post_harvest_supply = 1.0 if 6 <= month <= 10 else 0.5 if month == 11 else 0.0
        features.update(
            {
                "onion_storage_depletion_idx": depletion,
                "onion_harvest_proximity_60d": harvest_proximity,
                "onion_storage_scarcity_risk": depletion if month in {12, 1, 2, 3, 4} else 0.0,
                "onion_post_harvest_supply_pressure": post_harvest_supply,
                "onion_autumn_storage_transition": 1.0 if month in {9, 10} else 0.0,
                "onion_june_rebound_14d": 1.0 if month == 6 else 0.0,
                "onion_autumn_14d_correction": 1.0 if month in {9, 10} else 0.0,
            }
        )
    elif item_code == "garlic":
        storage_month = _months_since_harvest(month, harvest_month=5, max_months=10)
        scarcity = 0.6 if month == 2 else 0.85 if month == 3 else 1.0 if month == 4 else 0.0
        harvest_pressure = 1.0 if month in {5, 6} else 0.0
        features.update(
            {
                "garlic_storage_month_idx": storage_month,
                "garlic_scarcity_risk": scarcity,
                "garlic_winter_cold_damage": _positive(2.0 - temp) / 20.0 if month in {12, 1, 2} else 0.0,
                "garlic_harvest_pressure": harvest_pressure,
                "garlic_post_harvest_down_pressure": 1.0 if 5 <= month <= 8 else 0.0,
                "garlic_june_post_harvest_softening_14d": 1.0 if month == 6 else 0.5 if month == 7 else 0.0,
            }
        )
    elif item_code == "green_onion":
        heat = _positive(temp - 30.0) / 15.0
        cold = _positive(2.0 - temp) / 20.0
        heavy_rain = _safe_log_norm(rainfall)
        disruption = min(1.0, heat * 0.4 + cold * 0.4 + heavy_rain * 0.2 + supply_alert * 0.2)
        features.update(
            {
                "green_onion_heat_stress": heat,
                "green_onion_cold_damage": cold,
                "green_onion_heavy_rain": heavy_rain,
                "green_onion_supply_disruption": disruption,
                "green_onion_summer_down_pressure": 1.0 if month in {7, 8} else 0.0,
                "green_onion_late_june_normalization": 1.0 if month == 6 and base_date.day >= 20 else 0.0,
                "green_onion_august_14d_down_pressure": 1.0 if month == 8 else 0.5 if month == 7 else 0.0,
            }
        )
    return {key: round(value, 6) for key, value in features.items()}


def _cabbage_phase(month: int) -> int:
    if 3 <= month <= 6:
        return 0
    if 7 <= month <= 9:
        return 1
    if 10 <= month <= 11:
        return 2
    return 3


def _onion_storage_depletion(month: int) -> float:
    if month == 12:
        return 0.3
    if month == 1:
        return 0.5
    if month == 2:
        return 0.7
    if month == 3:
        return 0.9
    if month == 4:
        return 1.0
    return 0.0


def _months_since_harvest(month: int, harvest_month: int, max_months: int) -> float:
    elapsed = month - harvest_month if month >= harvest_month else month + (12 - harvest_month)
    return min(max(elapsed, 0), max_months) / max_months


def _event_proximity(base_date: date, event_month: int, event_day: int, window_days: int) -> float:
    event = date(base_date.year, event_month, event_day)
    if event < base_date:
        event = date(base_date.year + 1, event_month, event_day)
    days = abs((event - base_date).days)
    return round(max(0.0, 1.0 - days / window_days), 6)


def _positive(value: float) -> float:
    return max(0.0, value)


def _future_value_on_or_after(series: list[tuple[date, float]], idx: int, target_day: date) -> float | None:
    for future_day, future_value in series[idx + 1 :]:
        if future_day >= target_day:
            return future_value
    return None


def _returns(values: list[float]) -> list[float]:
    return [_pct_change(values[idx], values[idx - 1]) for idx in range(1, len(values))]


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / previous, 6)


def _safe_read_list(path: Path) -> list[Any]:
    try:
        payload = read_json(path)
    except (OSError, ValueError):
        return []
    return payload if isinstance(payload, list) else []


def _append_float(values: list[float], value: Any) -> None:
    parsed = _optional_float(value)
    if parsed is not None:
        values.append(parsed)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    raw = str(value)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except (ValueError, TypeError):
        return None


def _safe_log_norm(value: float | None) -> float:
    if value is None or value <= 0:
        return 0.0
    import math

    return round(math.log1p(value) / 20.0, 6)


def _auction_variant_share_features(raw: dict[str, Any]) -> dict[str, float]:
    variant_qty = raw.get("variant_qty") if isinstance(raw.get("variant_qty"), dict) else {}
    total = sum(_as_float(value) for value in variant_qty.values())
    if total <= 0:
        return {
            "auction_dominant_share": 0.0,
            "auction_seasonal_share": 0.0,
            "auction_stored_share": 0.0,
            "auction_processed_share": 0.0,
            "auction_imported_share": 0.0,
        }

    def share(predicate: Any) -> float:
        return sum(_as_float(value) for key, value in variant_qty.items() if predicate(str(key))) / total

    dominant = _as_float(raw.get("dominant_variant_share"))
    return {
        "auction_dominant_share": dominant,
        "auction_seasonal_share": share(lambda key: key.startswith("season_") or key in {"early", "mid", "late", "fresh"}),
        "auction_stored_share": share(lambda key: key == "stored" or key.startswith("stored_")),
        "auction_processed_share": share(lambda key: key in {"processed", "peeled", "peeled_daeseo", "peeled_namdo", "stem", "bunched"}),
        "auction_imported_share": share(lambda key: key == "imported"),
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _cyclical_sin(value: int, period: int) -> float:
    import math

    return round(math.sin(2 * math.pi * value / period), 6)


def _cyclical_cos(value: int, period: int) -> float:
    import math

    return round(math.cos(2 * math.pi * value / period), 6)


if __name__ == "__main__":
    sys.exit(main())
