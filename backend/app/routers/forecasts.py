from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select
from app.database import get_db
from app.models.item import Item
from app.models.forecast import Forecast
from app.models.price import DailyPrice
from app.models.signal import RegionSignal
from app.schemas.forecast import ForecastResponse, TopFactor
from datetime import date
from app.timezone import kst_today

router = APIRouter(prefix="/api/v1/items", tags=["forecasts"])


@router.get("/{item_code}/forecast", response_model=ForecastResponse)
async def get_forecast(
    item_code: str,
    target_date: str = None,
    horizon: int = 14,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404
        })

    base_date = date.fromisoformat(target_date) if target_date else kst_today()

    fc_result = await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
            Forecast.horizon_days == horizon,
        ).order_by(Forecast.created_at.desc())
    )
    fc = fc_result.scalar_one_or_none()

    if not fc:
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜 horizon={horizon}일 예측 데이터가 없습니다.",
            "code": 404
        })

    direction = fc.direction or fc.direction_14d
    up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d

    return ForecastResponse(
        item_code=fc.item_code,
        item_name=item.item_name,
        base_date=str(fc.base_date),
        model_version=fc.model_version,
        model_scope=_model_scope(fc),
        forecast={
            "horizon_days": fc.horizon_days,
            "direction": direction,
            "up_probability": up_prob,
            "direction_14d": fc.direction_14d,
            "up_probability_14d": fc.up_probability_14d,
            "surge_probability_14d": fc.surge_probability_14d,
            "volatility_risk_30d": fc.volatility_risk_30d,
            "bottom_probability": fc.bottom_probability,
        },
        top_factors=[TopFactor(**f) for f in (fc.top_factors or [])],
        national_supply_shock=fc.national_supply_shock,
        confidence=fc.confidence,
        summary=_build_summary(fc, item.item_name, horizon),
    )


@router.get("/{item_code}/forecasts")
async def get_all_horizons(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    """14/30/60/90일 예측을 한 번에 반환."""
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"error": "item_not_found", "code": 404})

    base_date = date.fromisoformat(target_date) if target_date else kst_today()

    fc_rows = (await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
        ).order_by(Forecast.horizon_days)
    )).scalars().all()

    if not fc_rows:
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜의 예측 데이터가 없습니다.",
            "code": 404,
        })

    horizons = {}
    for fc in fc_rows:
        direction = fc.direction or fc.direction_14d
        up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d
        horizons[str(fc.horizon_days)] = {
            "horizon_days": fc.horizon_days,
            "direction": direction,
            "up_probability": up_prob,
            "bottom_probability": fc.bottom_probability,
            "confidence": fc.confidence,
            "model_version": fc.model_version,
        }

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "base_date": str(base_date),
        "horizons": horizons,
    }


def _build_summary(fc: Forecast, item_name: str, horizon: int = 14) -> str:
    direction_map = {"up": "상승", "down": "하락", "neutral": "보합"}
    direction = direction_map.get(fc.direction or fc.direction_14d or "", "불명확")
    up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d
    prob = int((up_prob or 0) * 100)
    label = {7: "1주", 14: "2주", 21: "3주", 28: "4주", 30: "1개월", 60: "2개월", 90: "3개월"}.get(horizon, f"{horizon}일")
    return f"{item_name}은(는) {label} 내 {direction} 가능성이 {prob}%입니다."


def _model_scope(fc: Forecast) -> str:
    for factor in fc.top_factors or []:
        if not isinstance(factor, dict):
            continue
        name = str(factor.get("factor") or "")
        if name.startswith("model_scope_"):
            return name.replace("model_scope_", "", 1)
    if fc.model_version and fc.model_version.endswith("_item"):
        return "item"
    return "global"


@router.get("/{item_code}/forecast/explanation")
async def get_forecast_explanation(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    item, fc, base_date = await _load_item_forecast(item_code, target_date, db)
    model_scope = _model_scope(fc)
    latest_price_date = (
        await db.execute(
            select(func.max(DailyPrice.date)).where(DailyPrice.item_code == item_code)
        )
    ).scalar()
    latest_signal_date = (
        await db.execute(
            select(func.max(RegionSignal.date)).where(RegionSignal.item_code == item_code)
        )
    ).scalar()
    signal_result = await db.execute(
        select(RegionSignal)
        .where(RegionSignal.item_code == item_code, RegionSignal.date == base_date)
        .order_by(desc(RegionSignal.risk_score))
        .limit(3)
    )

    return {
        "item_code": fc.item_code,
        "item_name": item.item_name,
        "base_date": str(fc.base_date),
        "headline": _build_explanation_headline(fc, item.item_name),
        "model": {
            "version": fc.model_version,
            "scope": model_scope,
            "scope_label": "품목 전용 모델" if model_scope == "item" else "공통 모델",
            "confidence": fc.confidence,
            "confidence_label": _confidence_label(fc.confidence),
            "confidence_reason": _confidence_reason(fc, model_scope, latest_price_date, latest_signal_date, base_date),
            "confidence_factors": _confidence_factors(fc, model_scope, latest_price_date, latest_signal_date, base_date),
        },
        "forecast": {
            "direction_14d": fc.direction_14d,
            "direction_label": _direction_label(fc.direction_14d),
            "up_probability_14d": fc.up_probability_14d,
            "up_probability_label": _percent_label(fc.up_probability_14d),
            "surge_probability_14d": fc.surge_probability_14d,
            "volatility_risk_30d": fc.volatility_risk_30d,
            "bottom_probability": fc.bottom_probability,
            "national_supply_shock": fc.national_supply_shock,
        },
        "reasons": [_factor_reason(factor) for factor in (fc.top_factors or [])],
        "risk_regions": [_risk_region(region) for region in signal_result.scalars().all()],
        "data_freshness": {
            "price": _freshness(latest_price_date, base_date, warn_after_days=2),
            "region_signal": _freshness(latest_signal_date, base_date, warn_after_days=1),
            "forecast": _freshness(fc.base_date, base_date, warn_after_days=1),
        },
        "notes": _explanation_notes(model_scope, latest_price_date, latest_signal_date, base_date),
        "disclaimer": ForecastResponse.model_fields["disclaimer"].default,
    }


async def _load_item_forecast(
    item_code: str,
    target_date: str | None,
    db: AsyncSession,
    horizon: int = 14,
) -> tuple[Item, Forecast, date]:
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404,
        })

    base_date = date.fromisoformat(target_date) if target_date else kst_today()
    fc_result = await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
            Forecast.horizon_days == horizon,
        ).order_by(Forecast.created_at.desc())
    )
    fc = fc_result.scalar_one_or_none()
    if not fc:
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜의 예측 데이터가 없습니다. 파이프라인을 먼저 실행하세요.",
            "code": 404,
        })
    return item, fc, base_date


def _direction_label(direction: str | None) -> str:
    return {"up": "상승", "down": "하락", "neutral": "보합"}.get(direction or "", "불확실")


def _confidence_label(confidence: str | None) -> str:
    return {"high": "높음", "medium": "보통", "low": "낮음"}.get(confidence or "", "보통")


def _confidence_reason(
    fc: Forecast,
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> str:
    factors = _confidence_factors(fc, model_scope, latest_price_date, latest_signal_date, base_date)
    weak_factors = [factor for factor in factors if factor["status"] in {"weak", "missing"}]
    if fc.confidence == "high" and not weak_factors:
        return "Backtest calibration and current inputs support a high-confidence forecast."
    if weak_factors:
        labels = ", ".join(str(factor["label"]) for factor in weak_factors[:2])
        return f"Confidence is limited by {labels}."
    if fc.confidence == "medium":
        return "Forecast inputs are usable, but uncertainty remains in the recent signal mix."
    return "Confidence is conservative until more recent item-level history is available."


def _confidence_factors(
    fc: Forecast,
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> list[dict[str, str]]:
    price_status = _freshness(latest_price_date, base_date, warn_after_days=2)["status"]
    signal_status = _freshness(latest_signal_date, base_date, warn_after_days=1)["status"]
    risk_factor_count = sum(
        1
        for factor in (fc.top_factors or [])
        if isinstance(factor, dict) and str(factor.get("factor") or "") != "price_lag_model"
    )
    return [
        {
            "key": "model_scope",
            "label": "item model" if model_scope == "item" else "global model",
            "status": "strong" if model_scope == "item" else "medium",
        },
        {
            "key": "price_freshness",
            "label": "price data freshness",
            "status": "strong" if price_status == "fresh" else ("weak" if price_status == "stale" else "missing"),
        },
        {
            "key": "signal_freshness",
            "label": "risk signal freshness",
            "status": "strong" if signal_status == "fresh" else ("weak" if signal_status == "stale" else "missing"),
        },
        {
            "key": "risk_context",
            "label": "risk context",
            "status": "strong" if risk_factor_count > 0 else "weak",
        },
    ]


def _percent_label(value: float | None) -> str:
    if value is None:
        return "정보 없음"
    return f"{round(value * 100)}%"


def _build_explanation_headline(fc: Forecast, item_name: str) -> str:
    return (
        f"{item_name}은 향후 14일 기준 {_direction_label(fc.direction_14d)} 가능성이 "
        f"{_percent_label(fc.up_probability_14d)}로 계산되었습니다."
    )


def _factor_reason(factor: dict) -> dict:
    name = str(factor.get("factor") or "")
    direction = str(factor.get("direction") or "up")
    contribution = float(factor.get("contribution") or 0.0)
    label_map = {
        "price_lag_model": "최근 가격 흐름",
        "risk_overlay": "주산지 위험 보정",
    }
    message_map = {
        ("price_lag_model", "up"): "최근 가격 흐름이 상승 쪽으로 기울었습니다.",
        ("price_lag_model", "down"): "최근 가격 흐름이 하락 쪽으로 기울었습니다.",
        ("risk_overlay", "up"): "주산지 위험 신호가 가격 상승 압력을 더했습니다.",
        ("risk_overlay", "down"): "주산지 위험 신호가 가격 상승 압력을 낮췄습니다.",
    }
    return {
        "factor": name,
        "label": label_map.get(name, name or "기타 요인"),
        "direction": direction,
        "direction_label": _direction_label(direction),
        "contribution": contribution,
        "message": message_map.get((name, direction), "모델 계산에 반영된 요인입니다."),
    }


def _risk_region(region: RegionSignal) -> dict:
    return {
        "region_code": region.region_code,
        "region_name": region.region_name,
        "risk_score": region.risk_score,
        "risk_level": region.risk_level,
        "price_effect": region.price_effect,
        "summary": region.summary_text,
    }


def _freshness(latest_date: date | None, base_date: date, warn_after_days: int) -> dict:
    if latest_date is None:
        return {
            "latest_date": None,
            "lag_days": None,
            "status": "missing",
            "warn_after_days": warn_after_days,
        }
    lag_days = (base_date - latest_date).days
    if lag_days <= warn_after_days:
        status = "fresh"
    elif lag_days <= warn_after_days + 2:
        status = "stale"
    else:
        status = "missing"
    return {
        "latest_date": str(latest_date),
        "lag_days": lag_days,
        "status": status,
        "warn_after_days": warn_after_days,
    }


def _explanation_notes(
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> list[str]:
    notes = []
    if model_scope == "global":
        notes.append("아직 품목 전용 모델보다 공통 모델의 검증 성능이 더 안정적이어서 공통 모델을 사용했습니다.")
    else:
        notes.append("해당 품목의 검증 성능 기준을 통과한 품목 전용 모델을 사용했습니다.")
    if latest_price_date and latest_price_date < base_date:
        notes.append(f"가격 데이터 최신일은 {latest_price_date}로, 기준일보다 {(base_date - latest_price_date).days}일 늦습니다.")
    if latest_signal_date and latest_signal_date < base_date:
        notes.append(f"주산지 위험 신호 최신일은 {latest_signal_date}입니다.")
    return notes
