from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.database import get_db
from app.models.signal import RegionSignal
from app.models.forecast import Forecast
from app.models.price import DailyPrice
from app.schemas.signal import RegionSignalResponse
from app.pipeline.explain import build_summary_text, factors_to_display, ITEM_NAMES
from datetime import date, timedelta

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


@router.get("/api/v1/report/today")
async def get_today_report(db: AsyncSession = Depends(get_db)):
    """일일 리포트 — 기획서 26번 (JSON)
    오늘의 위험 품목 순위 + 지역 + 가격 변동 + 14일 예측 + 자연어 요약
    """
    today = date.today()
    start_30d = today - timedelta(days=30)

    # 전체 품목 예측
    fc_res = await db.execute(
        select(Forecast)
        .where(Forecast.base_date == today)
        .order_by(desc(Forecast.up_probability_14d))
    )
    forecasts = fc_res.scalars().all()

    # 오늘 지역 신호 최고 위험
    sig_res = await db.execute(
        select(RegionSignal).where(RegionSignal.date == today)
    )
    signals = sig_res.scalars().all()
    item_hotspot: dict[str, dict] = {}
    for s in signals:
        if s.item_code not in item_hotspot or s.risk_score > item_hotspot[s.item_code]["risk_score"]:
            item_hotspot[s.item_code] = {
                "region_name": s.region_name,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "summary": s.summary_text,
            }

    # 가격 변동 (최근 30일 → 최신 vs 30일전)
    price_res = await db.execute(
        select(DailyPrice)
        .where(DailyPrice.date >= start_30d)
        .order_by(DailyPrice.item_code, DailyPrice.date)
    )
    all_prices = price_res.scalars().all()
    price_by_item: dict[str, list] = {}
    for p in all_prices:
        price_by_item.setdefault(p.item_code, []).append(p)

    def price_change_30d(rows):
        if len(rows) < 2:
            return None
        latest = rows[-1].wholesale_price
        oldest = rows[0].wholesale_price
        if not oldest:
            return None
        return round((latest - oldest) / oldest * 100, 1)

    # 리포트 조립
    items_report = []
    for fc in forecasts:
        hotspot = item_hotspot.get(fc.item_code, {})
        prows = price_by_item.get(fc.item_code, [])
        change_30d = price_change_30d(prows)
        latest_price = prows[-1].wholesale_price if prows else None

        summary = build_summary_text(
            fc.item_code,
            fc.direction_14d,
            fc.up_probability_14d,
            fc.top_factors,
            fc.confidence,
        )
        display_factors = factors_to_display(fc.top_factors)

        items_report.append({
            "item_code": fc.item_code,
            "item_name": ITEM_NAMES.get(fc.item_code, fc.item_code),
            "forecast": {
                "direction_14d": fc.direction_14d,
                "up_probability_14d": fc.up_probability_14d,
                "surge_probability_14d": fc.surge_probability_14d,
                "volatility_risk": fc.volatility_risk_30d,
                "confidence": fc.confidence,
            },
            "price": {
                "latest": latest_price,
                "change_30d_pct": change_30d,
            },
            "hotspot": hotspot,
            "summary": summary,
            "top_factors": display_factors,
        })

    # 위험도 높은 순 정렬 (hotspot risk_score 기준)
    items_report.sort(
        key=lambda x: x["hotspot"].get("risk_score", 0), reverse=True
    )

    return {
        "report_date": str(today),
        "generated_at": str(date.today()),
        "item_count": len(items_report),
        "items": items_report,
    }
