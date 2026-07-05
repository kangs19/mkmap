from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_DATA_DIR = REPO_ROOT / "data" / "model"


def load_horizon_forecast(item_code: str, target_date: str | None = None) -> dict[str, Any] | None:
    payload = _read_json(_active_predictions_path())
    if not payload:
        return None
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("item_code")) != item_code:
            continue
        base_date = str(item.get("base_date") or "")
        if target_date and base_date != target_date:
            return None
        return {
            "source": "horizon_file",
            "source_path": str(_active_predictions_path()),
            "model_version": _active_model_version(),
            **item,
        }
    return None


def load_horizon_explanation(item_code: str, target_date: str | None = None) -> dict[str, Any] | None:
    payload = _read_json(_active_explanations_path())
    if not payload:
        return None
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("item_code")) != item_code:
            continue
        base_date = str(item.get("base_date") or "")
        if target_date and base_date != target_date:
            return None
        return {
            "source": "horizon_file",
            "source_path": str(_active_explanations_path()),
            "model_version": _active_model_version(),
            "held_horizons": payload.get("held_horizons", []),
            **item,
        }
    return None


def horizon_response(item: Any, forecast: dict[str, Any]) -> dict[str, Any]:
    horizons = _normalized_horizons(forecast.get("horizons", {}))
    h14 = horizons.get("14")
    primary = _primary_horizon(horizons)
    return {
        "item_code": str(forecast.get("item_code") or item.item_code),
        "item_name": getattr(item, "item_name", None) or str(forecast.get("item_code") or ""),
        "base_date": str(forecast.get("base_date") or ""),
        "model_version": str(forecast.get("model_version") or _active_model_version()),
        "model_scope": _combined_model_scope(horizons),
        "forecast": {
            "direction_14d": _backend_direction(h14.get("risk_adjusted_direction") if h14 else None),
            "up_probability_14d": h14.get("up_probability") if h14 else None,
            "surge_probability_14d": h14.get("surge_probability") if h14 else None,
            "volatility_risk_30d": _volatility_risk(horizons.get("30")),
            "bottom_probability": _bottom_probability(primary),
            "active_horizons": [int(key) for key in sorted(horizons, key=lambda value: int(value))],
            "horizons": horizons,
        },
        "top_factors": [],
        "national_supply_shock": None,
        "confidence": _combined_confidence(horizons),
        "summary": _summary(getattr(item, "item_name", None) or str(forecast.get("item_code") or ""), horizons),
        "source": "horizon_file",
    }


def horizon_explanation_response(item: Any, explanation: dict[str, Any]) -> dict[str, Any]:
    horizons = _normalized_horizons(explanation.get("horizons", {}))
    return {
        "item_code": str(explanation.get("item_code") or item.item_code),
        "item_name": getattr(item, "item_name", None) or str(explanation.get("item_code") or ""),
        "base_date": str(explanation.get("base_date") or ""),
        "headline": _summary(getattr(item, "item_name", None) or str(explanation.get("item_code") or ""), horizons),
        "model": {
            "version": str(explanation.get("model_version") or _active_model_version()),
            "scope": _combined_model_scope(horizons),
            "confidence": _combined_confidence(horizons),
        },
        "forecast": {
            "active_horizons": [int(key) for key in sorted(horizons, key=lambda value: int(value))],
            "horizons": horizons,
        },
        "reasons_by_horizon": {
            key: {
                "summary": row.get("summary"),
                "supporting_reasons": row.get("supporting_reasons", []),
                "offsetting_reasons": row.get("offsetting_reasons", []),
                "quality_gate": row.get("quality_gate", {}),
            }
            for key, row in horizons.items()
            if isinstance(row, dict)
        },
        "held_horizons": explanation.get("held_horizons", []),
        "source": "horizon_file",
    }


def _normalized_horizons(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            normalized_key = str(int(key))
        except (TypeError, ValueError):
            continue
        result[normalized_key] = value
    return result


def _primary_horizon(horizons: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in ("30", "90", "180", "365", "1", "14"):
        if key in horizons:
            return horizons[key]
    return None


def _combined_model_scope(horizons: dict[str, dict[str, Any]]) -> str:
    scopes = {str(row.get("model_scope") or "global") for row in horizons.values()}
    if "item" in scopes and "global" in scopes:
        return "mixed"
    if "item" in scopes:
        return "item"
    return "global"


def _combined_confidence(horizons: dict[str, dict[str, Any]]) -> str:
    values = [str(row.get("confidence") or "medium") for row in horizons.values()]
    if not values:
        return "low"
    if "low" in values:
        return "low"
    if "medium" in values:
        return "medium"
    return "high"


def _backend_direction(direction: Any) -> str | None:
    if direction == "stable":
        return "neutral"
    if direction in {"up", "down"}:
        return str(direction)
    return None


def _volatility_risk(horizon: dict[str, Any] | None) -> str | None:
    if not horizon:
        return None
    change = abs(float(horizon.get("risk_adjusted_change") or horizon.get("predicted_change") or 0.0))
    if change >= 0.15:
        return "high"
    if change >= 0.07:
        return "medium"
    return "low"


def _bottom_probability(horizon: dict[str, Any] | None) -> float | None:
    if not horizon:
        return None
    up_probability = horizon.get("up_probability")
    if up_probability is None:
        return None
    return round(max(0.0, min(1.0, 1.0 - float(up_probability))), 4)


def _summary(item_name: str, horizons: dict[str, dict[str, Any]]) -> str:
    if not horizons:
        return f"{item_name}: no active horizon forecast is available."
    parts = []
    for key in sorted(horizons, key=lambda value: int(value)):
        row = horizons[key]
        direction = row.get("risk_adjusted_direction") or row.get("predicted_direction") or "unknown"
        change = float(row.get("risk_adjusted_change") or row.get("predicted_change") or 0.0) * 100.0
        parts.append(f"{key}d {direction} {change:.1f}%")
    return f"{item_name} active forecast: " + ", ".join(parts)


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _active_model_version() -> str:
    return get_settings().active_price_model_prefix


@lru_cache(maxsize=8)
def _active_predictions_path() -> Path | None:
    settings = get_settings()
    if settings.active_price_predictions_path:
        return _resolve_path(settings.active_price_predictions_path)
    return _discover_latest("latest_price_horizon_predictions_*_temporal_strict_candidates.json")


@lru_cache(maxsize=8)
def _active_explanations_path() -> Path | None:
    settings = get_settings()
    if settings.active_price_explanations_path:
        return _resolve_path(settings.active_price_explanations_path)
    return _discover_latest("latest_price_horizon_explanations_*_temporal_strict_candidates.json")


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _discover_latest(pattern: str) -> Path | None:
    candidates = sorted(MODEL_DATA_DIR.glob(pattern), key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return candidates[0] if candidates else None
