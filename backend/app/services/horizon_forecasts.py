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
    confidence = _combined_confidence(horizons)
    model_scope = _combined_model_scope(horizons)
    base_date = str(explanation.get("base_date") or "")
    h14 = horizons.get("14")
    primary = h14 or _primary_horizon(horizons)
    direction = _backend_direction(primary.get("risk_adjusted_direction") if primary else None)
    up_probability = primary.get("up_probability") if primary else None
    reasons = _horizon_reasons(primary)
    phase_label = _horizon_phase_label(int(primary.get("horizon_days") or 14) if primary else 14)
    return {
        "item_code": str(explanation.get("item_code") or item.item_code),
        "item_name": getattr(item, "item_name", None) or str(explanation.get("item_code") or ""),
        "base_date": base_date,
        "headline": _summary(getattr(item, "item_name", None) or str(explanation.get("item_code") or ""), horizons),
        "direction": direction,
        "direction_label": _direction_label(direction),
        "up_probability_14d": up_probability,
        "up_probability_label": _percent_label(up_probability),
        "model": {
            "version": str(explanation.get("model_version") or _active_model_version()),
            "scope": model_scope,
            "confidence": confidence,
            "confidence_reason": _horizon_confidence_reason(confidence, model_scope, horizons),
            "confidence_factors": _horizon_confidence_factors(model_scope, horizons),
        },
        "forecast": {
            "direction_14d": direction,
            "direction_label": _direction_label(direction),
            "up_probability_14d": up_probability,
            "up_probability_label": _percent_label(up_probability),
            "active_horizons": [int(key) for key in sorted(horizons, key=lambda value: int(value))],
            "horizons": horizons,
        },
        "pressure_summary": _pressure_summary(direction, up_probability, reasons, phase_label),
        "reason_groups": _reason_groups(reasons),
        "reasons": reasons,
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
        "data_freshness": {
            "price": {"status": "unknown", "latest_date": base_date or None},
            "region_signal": {"status": "unknown", "latest_date": None},
            "forecast": {"status": "fresh" if base_date else "unknown", "latest_date": base_date or None},
        },
        "source": "horizon_file",
    }


def _horizon_confidence_reason(
    confidence: str,
    model_scope: str,
    horizons: dict[str, dict[str, Any]],
) -> str:
    held = [key for key, row in horizons.items() if row.get("held_out")]
    if confidence == "high" and model_scope in {"item", "mixed"}:
        return "Active horizon model outputs are available with item-level or mixed item/global coverage."
    if held:
        return f"Some horizons are held back by quality gates: {', '.join(sorted(held, key=int))}d."
    return "Confidence is based on the available active horizon forecast file."


def _horizon_confidence_factors(
    model_scope: str,
    horizons: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    active_count = len(horizons)
    held_count = sum(1 for row in horizons.values() if row.get("held_out"))
    return [
        {
            "key": "model_scope",
            "label": "item/global horizon coverage",
            "status": "strong" if model_scope in {"item", "mixed"} else "medium",
        },
        {
            "key": "active_horizons",
            "label": f"{active_count} active horizons",
            "status": "strong" if active_count >= 3 else ("medium" if active_count else "missing"),
        },
        {
            "key": "quality_gate",
            "label": "horizon quality gates",
            "status": "weak" if held_count else "strong",
        },
    ]


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


def _direction_label(direction: str | None) -> str:
    return {"up": "상승", "down": "하락", "neutral": "보합"}.get(direction or "", "불확실")


def _percent_label(value: Any) -> str:
    if value is None:
        return "정보 없음"
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "정보 없음"


def _horizon_phase_label(horizon_days: int) -> str:
    if horizon_days <= 21:
        return "단기(1~3주)"
    if horizon_days <= 90:
        return "중기(1~3개월)"
    return "장기(3개월 이상)"


def _horizon_reasons(horizon: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not horizon:
        return []
    rows = []
    for source_key in ("supporting_reasons", "offsetting_reasons"):
        raw_rows = horizon.get(source_key, [])
        if not isinstance(raw_rows, list):
            continue
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            contribution = _float_or_none(row.get("contribution"))
            direction = "neutral"
            if contribution is not None and contribution > 0:
                direction = "up"
            elif contribution is not None and contribution < 0:
                direction = "down"
            label = str(row.get("label") or row.get("feature") or "모델 요인")
            effect = row.get("effect")
            pct = _float_or_none(row.get("contribution_pct_points"))
            if pct is not None:
                message = f"{label} 요인이 예측 등락률에 {pct:+.2f}%p 반영됐습니다."
            elif effect:
                message = f"{label} 요인이 {effect}으로 반영됐습니다."
            else:
                message = f"{label} 요인이 모델 판단에 반영됐습니다."
            rows.append({
                "factor": str(row.get("feature") or ""),
                "label": label,
                "direction": direction,
                "direction_label": _direction_label(direction),
                "contribution": contribution,
                "message": message,
                "source": source_key,
            })
    rows.sort(key=lambda item: abs(float(item.get("contribution") or 0.0)), reverse=True)
    return rows[:8]


def _reason_groups(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = {
        "up": ("상승 압력", "값을 올릴 수 있는 요인"),
        "down": ("하락 압력", "값을 낮출 수 있는 요인"),
        "neutral": ("확인할 변수", "방향보다 점검이 필요한 요인"),
    }
    groups = []
    for direction in ("up", "down", "neutral"):
        items = [reason for reason in reasons if (reason.get("direction") or "neutral") == direction]
        if not items:
            continue
        title, hint = labels[direction]
        groups.append({
            "direction": direction,
            "title": title,
            "hint": hint,
            "count": len(items),
            "items": items,
        })
    return groups


def _pressure_summary(
    direction: str | None,
    up_probability: Any,
    reasons: list[dict[str, Any]],
    phase_label: str,
) -> dict[str, Any]:
    up_count = sum(1 for reason in reasons if reason.get("direction") == "up")
    down_count = sum(1 for reason in reasons if reason.get("direction") == "down")
    neutral_count = sum(1 for reason in reasons if (reason.get("direction") or "neutral") == "neutral")
    mixed_pressure = up_count > 0 and down_count > 0

    if direction == "up":
        title = f"결론: {phase_label}에는 상승 쪽을 더 봅니다"
        body = "모델 확률은 상승 쪽을 가리킵니다. 다만 하락 압력이 함께 있으면 반대 변수를 같이 확인해야 합니다."
        color, bg, summary_direction = "#c02828", "#fff0f0", "up"
    elif direction == "down":
        title = f"결론: {phase_label}에는 하락 쪽을 더 봅니다"
        body = "모델 확률은 하락 쪽을 가리킵니다. 다만 상승 압력이 함께 있으면 반대 변수를 같이 확인해야 합니다."
        color, bg, summary_direction = "#1a8a1a", "#f0fff0", "down"
    elif direction == "neutral" and up_probability is not None:
        title = f"결론: {phase_label}에는 보합 가능성이 큽니다"
        body = "상승과 하락 요인이 비슷하거나 변화폭이 작아, 큰 방향보다 변동 리스크를 봐야 합니다."
        color, bg, summary_direction = "#6a1e9a", "#f5f0ff", "neutral"
    elif mixed_pressure:
        title = f"결론: {phase_label}에는 방향이 엇갈립니다"
        body = f"상승 압력 {up_count}개와 하락 압력 {down_count}개가 동시에 있습니다. 어느 변수가 먼저 움직이는지가 중요합니다."
        color, bg, summary_direction = "#a07010", "#fff9e6", "mixed"
    elif up_count > down_count:
        title = f"결론: {phase_label}에는 상승 압력을 먼저 봅니다"
        body = "다만 확률 데이터가 부족해 예측값이 아니라 요인 분석으로만 표시합니다."
        color, bg, summary_direction = "#c02828", "#fff0f0", "up_pressure"
    elif down_count > up_count:
        title = f"결론: {phase_label}에는 하락 압력을 먼저 봅니다"
        body = "다만 확률 데이터가 부족해 예측값이 아니라 요인 분석으로만 표시합니다."
        color, bg, summary_direction = "#1a8a1a", "#f0fff0", "down_pressure"
    else:
        title = f"결론: {phase_label}에는 추가 데이터가 필요합니다"
        body = f"참고 요인 {neutral_count}개가 있지만 상승/하락 판단을 낼 만큼의 모델 신호가 부족합니다."
        color, bg, summary_direction = "#6a1e9a", "#f5f0ff", "insufficient_data"

    return {
        "direction": summary_direction,
        "title": title,
        "body": body,
        "color": color,
        "bg": bg,
        "up_probability": _float_or_none(up_probability),
        "up_count": up_count,
        "down_count": down_count,
        "neutral_count": neutral_count,
        "mixed_pressure": mixed_pressure,
    }


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
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
