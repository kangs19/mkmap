from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import delete


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.database import AsyncSessionLocal, init_db
from app.models.forecast import Forecast
from app.models.signal import RegionSignal


DEFAULT_MODEL_VERSION = "mkmap_meta_hybrid_linear_risk_overlay_v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import mkmap_meta JSON outputs into backend DB tables.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--signals", default=None, help="Path to data/signals/YYYYMMDD/region_risk_signals.json")
    parser.add_argument("--predictions", default=None, help="Path to latest_price_predictions*.json")
    parser.add_argument("--skip-signals", action="store_true")
    parser.add_argument("--skip-forecasts", action="store_true")
    return parser.parse_args()


def dated_default_paths(target_date: date) -> tuple[Path, Path]:
    stamp = f"{target_date:%Y%m%d}"
    return (
        REPO_ROOT / "data" / "signals" / stamp / "region_risk_signals.json",
        REPO_ROOT / "data" / "model" / f"latest_price_predictions_{stamp}_risk.json",
    )


async def import_signals(path: Path, target_date: date) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Signal payload must be a list: {path}")

    rows: list[RegionSignal] = []
    item_codes: set[str] = set()
    for item_payload in payload:
        if not isinstance(item_payload, dict):
            continue
        item_code = str(item_payload.get("item_code") or "")
        if not item_code:
            continue
        item_codes.add(item_code)
        data_status = item_payload.get("data_status") if isinstance(item_payload.get("data_status"), dict) else {}
        for signal in item_payload.get("signals") or []:
            if not isinstance(signal, dict):
                continue
            top_factors = signal.get("top_factors") if isinstance(signal.get("top_factors"), list) else []
            rows.append(
                RegionSignal(
                    item_code=item_code,
                    region_code=str(signal.get("region_code") or ""),
                    region_name=str(signal.get("region_name") or ""),
                    date=target_date,
                    risk_score=round(float(signal.get("risk_score") or 0.0) * 100, 2),
                    risk_level=_backend_risk_level(str(signal.get("risk_level") or "normal")),
                    supply_shock=_supply_shock(signal),
                    price_effect=_backend_price_effect(str(signal.get("price_effect") or "stable")),
                    weather_summary=_weather_summary(top_factors, data_status),
                    market_summary=_market_summary(signal, data_status),
                    summary_text=signal.get("summary"),
                )
            )

    async with AsyncSessionLocal() as db:
        for item_code in item_codes:
            await db.execute(
                delete(RegionSignal).where(
                    RegionSignal.item_code == item_code,
                    RegionSignal.date == target_date,
                )
            )
        db.add_all(rows)
        await db.commit()

    return len(rows)


async def import_forecasts(path: Path, target_date: date) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Prediction payload must be a list: {path}")

    rows: list[Forecast] = []
    item_codes: set[str] = set()
    for prediction in payload:
        if not isinstance(prediction, dict):
            continue
        item_code = str(prediction.get("item_code") or "")
        if not item_code:
            continue
        item_codes.add(item_code)
        adjusted_change = float(prediction.get("risk_adjusted_next_change", prediction.get("predicted_next_change", 0.0)) or 0.0)
        pure_change = float(prediction.get("predicted_next_change") or 0.0)
        risk_overlay = prediction.get("risk_overlay") if isinstance(prediction.get("risk_overlay"), dict) else {}
        model_scope = str(prediction.get("model_scope") or "global")
        rows.append(
            Forecast(
                item_code=item_code,
                base_date=target_date,
                model_version=_model_version(model_scope),
                direction_14d=_forecast_direction(str(prediction.get("risk_adjusted_direction") or prediction.get("predicted_direction") or "stable")),
                up_probability_14d=_change_to_probability(adjusted_change),
                surge_probability_14d=_change_to_surge_probability(adjusted_change),
                volatility_risk_30d=_volatility_risk(risk_overlay),
                bottom_probability=round(1.0 - _change_to_probability(adjusted_change), 4),
                top_factors=_forecast_factors(prediction, pure_change, adjusted_change),
                national_supply_shock=round(adjusted_change - pure_change, 6),
                confidence="medium" if risk_overlay else "low",
            )
        )

    async with AsyncSessionLocal() as db:
        for item_code in item_codes:
            await db.execute(
                delete(Forecast).where(
                    Forecast.item_code == item_code,
                    Forecast.base_date == target_date,
                )
            )
        db.add_all(rows)
        await db.commit()

    return len(rows)


def _backend_risk_level(level: str) -> str:
    return {
        "normal": "normal",
        "watch": "caution",
        "warning": "warning",
        "critical": "high",
        "high": "high",
    }.get(level, "normal")


def _backend_price_effect(effect: str) -> str:
    if "up" in effect:
        return "up"
    if "down" in effect:
        return "down"
    return "neutral"


def _forecast_direction(direction: str) -> str:
    if direction == "up":
        return "up"
    if direction == "down":
        return "down"
    return "neutral"


def _change_to_probability(change: float) -> float:
    probability = 0.5 + max(-0.2, min(0.2, change * 5.0))
    return round(probability, 4)


def _change_to_surge_probability(change: float) -> float:
    probability = max(0.0, min(1.0, change / 0.08))
    return round(probability, 4)


def _volatility_risk(risk_overlay: dict[str, Any]) -> str:
    risk_score = float(risk_overlay.get("max_risk_score") or 0.0)
    if risk_score >= 0.45:
        return "high"
    if risk_score >= 0.25:
        return "medium"
    return "low"


def _model_version(model_scope: str) -> str:
    if model_scope == "item":
        return DEFAULT_MODEL_VERSION + "_item"
    return DEFAULT_MODEL_VERSION + "_global"


def _forecast_factors(prediction: dict[str, Any], pure_change: float, adjusted_change: float) -> list[dict[str, Any]]:
    overlay = prediction.get("risk_overlay") if isinstance(prediction.get("risk_overlay"), dict) else {}
    factors = [
        {
            "factor": "price_lag_model",
            "contribution": abs(round(pure_change, 6)),
            "direction": "up" if pure_change >= 0 else "down",
        },
        {
            "factor": "risk_overlay",
            "contribution": abs(round(adjusted_change - pure_change, 6)),
            "direction": "up" if adjusted_change >= pure_change else "down",
        },
    ]
    if overlay:
        factors.append(
            {
                "factor": overlay.get("top_factor") or "region_risk",
                "contribution": round(float(overlay.get("max_risk_score") or 0.0), 6),
                "direction": "up",
            }
        )
    return factors


def _supply_shock(signal: dict[str, Any]) -> float:
    top_factors = signal.get("top_factors") if isinstance(signal.get("top_factors"), list) else []
    for factor in top_factors:
        if isinstance(factor, dict) and factor.get("factor") == "production_region_weight":
            return round(float(factor.get("contribution") or 0.0), 4)
    return 0.0


def _weather_summary(top_factors: list[Any], data_status: dict[str, Any]) -> dict[str, Any]:
    weather_factor = next(
        (factor for factor in top_factors if isinstance(factor, dict) and factor.get("factor") == "weather_pressure"),
        None,
    )
    return {
        "feature_count": data_status.get("weather", 0),
        "weather_pressure": weather_factor.get("contribution") if weather_factor else 0,
    }


def _market_summary(signal: dict[str, Any], data_status: dict[str, Any]) -> dict[str, Any]:
    top_factors = signal.get("top_factors") if isinstance(signal.get("top_factors"), list) else []
    return {
        "price_feature_count": data_status.get("prices", 0),
        "event_feature_count": data_status.get("events", 0),
        "top_factors": top_factors,
    }


async def main_async() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    default_signals, default_predictions = dated_default_paths(target_date)
    signal_path = Path(args.signals) if args.signals else default_signals
    prediction_path = Path(args.predictions) if args.predictions else default_predictions

    await init_db()
    result: dict[str, Any] = {"date": target_date.isoformat()}

    if not args.skip_signals:
        result["signals_imported"] = await import_signals(signal_path, target_date)
    if not args.skip_forecasts:
        result["forecasts_imported"] = await import_forecasts(prediction_path, target_date)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
