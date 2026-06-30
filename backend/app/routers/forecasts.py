from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.item import Item
from app.models.forecast import Forecast
from app.schemas.forecast import ForecastResponse, TopFactor
from datetime import date

router = APIRouter(prefix="/api/v1/items", tags=["forecasts"])


@router.get("/{item_code}/forecast", response_model=ForecastResponse)
async def get_forecast(
    item_code: str,
    target_date: str = None,
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

    base_date = date.fromisoformat(target_date) if target_date else date.today()

    fc_result = await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date
        ).order_by(Forecast.created_at.desc())
    )
    fc = fc_result.scalar_one_or_none()

    if not fc:
        # 예측 데이터 없을 때 — 파이프라인 미실행 상태
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜의 예측 데이터가 없습니다. 파이프라인을 먼저 실행하세요.",
            "code": 404
        })

    return ForecastResponse(
        item_code=fc.item_code,
        item_name=item.item_name,
        base_date=str(fc.base_date),
        model_version=fc.model_version,
        model_scope=_model_scope(fc),
        forecast={
            "direction_14d": fc.direction_14d,
            "up_probability_14d": fc.up_probability_14d,
            "surge_probability_14d": fc.surge_probability_14d,
            "volatility_risk_30d": fc.volatility_risk_30d,
            "bottom_probability": fc.bottom_probability,
        },
        top_factors=[TopFactor(**f) for f in (fc.top_factors or [])],
        national_supply_shock=fc.national_supply_shock,
        confidence=fc.confidence,
        summary=_build_summary(fc, item.item_name),
    )


def _build_summary(fc: Forecast, item_name: str) -> str:
    direction_map = {"up": "상승", "down": "하락", "neutral": "보합"}
    direction = direction_map.get(fc.direction_14d, "불명확")
    prob = int((fc.up_probability_14d or 0) * 100)
    return f"{item_name}은(는) 14일 내 {direction} 가능성이 {prob}%입니다."


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
