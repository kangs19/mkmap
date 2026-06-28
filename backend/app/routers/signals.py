from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models.signal import RegionSignal
from app.models.forecast import Forecast
from app.schemas.signal import RegionSignalResponse
from datetime import date

router = APIRouter(tags=["signals"])


@router.get("/api/v1/items/{item_code}/regions/{region_code}/signal",
            response_model=RegionSignalResponse)
async def get_region_signal(
    item_code: str,
    region_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    base_date = date.fromisoformat(target_date) if target_date else date.today()

    result = await db.execute(
        select(RegionSignal).where(
            RegionSignal.item_code == item_code,
            RegionSignal.region_code == region_code,
            RegionSignal.date == base_date,
        )
    )
    signal = result.scalar_one_or_none()

    if not signal:
        raise HTTPException(status_code=404, detail={
            "error": "signal_not_found",
            "message": f"'{base_date}' 날짜의 지역 신호 데이터가 없습니다.",
            "code": 404
        })

    return RegionSignalResponse(
        item_code=signal.item_code,
        region_code=signal.region_code,
        region_name=signal.region_name,
        risk_score=signal.risk_score,
        risk_level=signal.risk_level,
        supply_shock=signal.supply_shock,
        price_effect=signal.price_effect,
        weather_summary=signal.weather_summary,
        market_summary=signal.market_summary,
        summary=signal.summary_text,
    )


@router.get("/api/v1/items/{item_code}/signals")
async def get_item_signals(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    """품목 전체 지역의 당일 위험 신호 목록"""
    base_date = date.fromisoformat(target_date) if target_date else date.today()
    result = await db.execute(
        select(RegionSignal).where(
            and_(
                RegionSignal.item_code == item_code,
                RegionSignal.date == base_date,
            )
        ).order_by(RegionSignal.risk_score.desc())
    )
    signals = result.scalars().all()
    return {
        "item_code": item_code,
        "base_date": str(base_date),
        "signals": [
            {
                "region_code": s.region_code,
                "region_name": s.region_name,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "supply_shock": s.supply_shock,
                "price_effect": s.price_effect,
                "weather_summary": s.weather_summary,
                "market_summary": s.market_summary,
                "summary": s.summary_text,
            }
            for s in signals
        ]
    }


@router.get("/api/v1/signals/today")
async def get_today_signals(db: AsyncSession = Depends(get_db)):
    """모든 품목의 오늘 예측 + 위험 신호 요약"""
    today = date.today()

    fc_result = await db.execute(
        select(Forecast).where(Forecast.base_date == today)
        .order_by(Forecast.up_probability_14d.desc())
    )
    forecasts = {f.item_code: f for f in fc_result.scalars().all()}

    sig_result = await db.execute(
        select(RegionSignal).where(RegionSignal.date == today)
    )
    signals = sig_result.scalars().all()

    # 품목별 최고 위험도 집계
    item_max_risk: dict[str, dict] = {}
    for s in signals:
        if s.item_code not in item_max_risk or s.risk_score > item_max_risk[s.item_code]["risk_score"]:
            item_max_risk[s.item_code] = {
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "hotspot_region": s.region_name,
            }

    items_out = []
    all_codes = set(list(forecasts.keys()) + list(item_max_risk.keys()))
    for code in sorted(all_codes):
        f = forecasts.get(code)
        risk = item_max_risk.get(code, {})
        items_out.append({
            "item_code": code,
            "direction_14d": f.direction_14d if f else None,
            "up_probability_14d": f.up_probability_14d if f else None,
            "volatility_risk": f.volatility_risk_30d if f else None,
            "confidence": f.confidence if f else None,
            "risk_score": risk.get("risk_score"),
            "risk_level": risk.get("risk_level"),
            "hotspot_region": risk.get("hotspot_region"),
        })

    return {"base_date": str(today), "items": items_out}
