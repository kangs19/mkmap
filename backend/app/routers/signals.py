from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from app.database import get_db
from app.models.item import Item
from app.models.signal import RegionSignal
from app.models.forecast import Forecast
from app.models.price import DailyPrice
from app.schemas.signal import RegionSignalResponse
from app.pipeline.explain import build_summary_text, factors_to_display, ITEM_NAMES
from datetime import date, timedelta
from app import cache
from app.timezone import kst_today

router = APIRouter(tags=["signals"])


@router.get("/api/v1/items/{item_code}/regions/{region_code}/signal",
            response_model=RegionSignalResponse)
async def get_region_signal(
    item_code: str,
    region_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    base_date = date.fromisoformat(target_date) if target_date else kst_today()

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
    base_date = date.fromisoformat(target_date) if target_date else kst_today()
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
    cached = cache.get("signals:today")
    if cached:
        return cached
    today = kst_today()

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

    result = {"base_date": str(today), "items": items_out}
    cache.set("signals:today", result, ttl=300)  # 5분 캐시
    return result


@router.get("/api/v1/dashboard/cards")
async def get_dashboard_cards(
    target_date: str = None,
    limit: int = 12,
    db: AsyncSession = Depends(get_db),
):
    """Compact public payload for dashboard item cards."""
    base_date = date.fromisoformat(target_date) if target_date else kst_today()
    start_30d = base_date - timedelta(days=30)
    limit = max(1, min(limit, 50))

    item_res = await db.execute(select(Item).where(Item.is_active == True).order_by(Item.item_code))
    items = {item.item_code: item for item in item_res.scalars().all()}

    fc_res = await db.execute(select(Forecast).where(Forecast.base_date == base_date))
    forecasts = {forecast.item_code: forecast for forecast in fc_res.scalars().all()}

    sig_res = await db.execute(select(RegionSignal).where(RegionSignal.date == base_date))
    hotspots: dict[str, RegionSignal] = {}
    for signal in sig_res.scalars().all():
        if signal.item_code not in hotspots or signal.risk_score > hotspots[signal.item_code].risk_score:
            hotspots[signal.item_code] = signal

    price_res = await db.execute(
        select(DailyPrice)
        .where(DailyPrice.date >= start_30d, DailyPrice.date <= base_date, DailyPrice.source == "kamis")
        .order_by(DailyPrice.item_code, DailyPrice.date)
    )
    price_by_item: dict[str, list[DailyPrice]] = {}
    for price in price_res.scalars().all():
        price_by_item.setdefault(price.item_code, []).append(price)

    item_codes = sorted(set(items) | set(forecasts) | set(hotspots) | set(price_by_item))
    cards = [
        _dashboard_card(
            item_code,
            items.get(item_code),
            forecasts.get(item_code),
            hotspots.get(item_code),
            price_by_item.get(item_code, []),
        )
        for item_code in item_codes
    ]
    cards.sort(key=_dashboard_card_rank, reverse=True)
    cards = cards[:limit]
    return {
        "base_date": str(base_date),
        "card_count": len(cards),
        "cards": cards,
    }


@router.get("/api/v1/alerts/high-risk")
async def get_high_risk_alerts(
    target_date: str = None,
    min_risk_score: float = 70.0,
    min_up_probability: float = 0.6,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """High-risk item/region combinations for alert surfaces."""
    base_date = date.fromisoformat(target_date) if target_date else kst_today()
    limit = max(1, min(limit, 100))
    min_risk_score = max(0.0, min(min_risk_score, 100.0))
    min_up_probability = max(0.0, min(min_up_probability, 1.0))

    item_res = await db.execute(select(Item).where(Item.is_active == True))
    items = {item.item_code: item for item in item_res.scalars().all()}

    fc_res = await db.execute(select(Forecast).where(Forecast.base_date == base_date))
    forecasts = {forecast.item_code: forecast for forecast in fc_res.scalars().all()}

    sig_res = await db.execute(
        select(RegionSignal)
        .where(RegionSignal.date == base_date, RegionSignal.risk_score >= min_risk_score)
        .order_by(desc(RegionSignal.risk_score))
    )
    alerts = [
        _high_risk_alert(signal, items.get(signal.item_code), forecasts.get(signal.item_code), min_risk_score, min_up_probability)
        for signal in sig_res.scalars().all()
    ]
    alerts = [alert for alert in alerts if alert["triggered_rules"]]
    alerts.sort(key=_alert_rank, reverse=True)
    alerts = alerts[:limit]

    return {
        "base_date": str(base_date),
        "thresholds": {
            "min_risk_score": min_risk_score,
            "min_up_probability": min_up_probability,
        },
        "alert_count": len(alerts),
        "alerts": alerts,
    }


def _dashboard_card(
    item_code: str,
    item: Item | None,
    forecast: Forecast | None,
    hotspot: RegionSignal | None,
    prices: list[DailyPrice],
) -> dict:
    latest_price = prices[-1].wholesale_price if prices else None
    price_change = _price_change_pct(prices)
    top_factors = factors_to_display(forecast.top_factors) if forecast else []
    direction = forecast.direction_14d if forecast else None
    probability = forecast.up_probability_14d if forecast else None
    confidence = forecast.confidence if forecast else None
    return {
        "item_code": item_code,
        "item_name": item.item_name if item else ITEM_NAMES.get(item_code, item_code),
        "summary": (
            build_summary_text(item_code, direction, probability, forecast.top_factors, confidence)
            if forecast
            else "예측 데이터가 아직 준비되지 않았습니다."
        ),
        "forecast": {
            "direction_14d": direction,
            "up_probability_14d": probability,
            "surge_probability_14d": forecast.surge_probability_14d if forecast else None,
            "bottom_probability": forecast.bottom_probability if forecast else None,
            "confidence": confidence,
            "model_scope": _card_model_scope(forecast),
        },
        "risk": {
            "score": hotspot.risk_score if hotspot else None,
            "level": hotspot.risk_level if hotspot else None,
            "price_effect": hotspot.price_effect if hotspot else None,
            "hotspot_region": hotspot.region_name if hotspot else None,
            "summary": hotspot.summary_text if hotspot else None,
        },
        "price": {
            "latest": latest_price,
            "change_30d_pct": price_change,
        },
        "top_factors": top_factors[:3],
    }


def _price_change_pct(prices: list[DailyPrice]) -> float | None:
    # 날짜별 1행으로 중복 제거 (같은 날짜 여러 소스 혼재 방지)
    by_date: dict = {}
    for p in prices:
        by_date[p.date] = p
    deduped = sorted(by_date.values(), key=lambda p: p.date)
    if len(deduped) < 2:
        return None
    oldest = deduped[0].wholesale_price
    latest = deduped[-1].wholesale_price
    if not oldest or not latest:
        return None
    return round((latest - oldest) / oldest * 100, 1)


def _card_model_scope(forecast: Forecast | None) -> str | None:
    if not forecast:
        return None
    if forecast.model_version and forecast.model_version.endswith("_item"):
        return "item"
    return "global"


def _dashboard_card_rank(card: dict) -> tuple[float, float]:
    risk_score = card.get("risk", {}).get("score") or 0.0
    probability = card.get("forecast", {}).get("up_probability_14d") or 0.0
    return float(risk_score), float(probability)


def _high_risk_alert(
    signal: RegionSignal,
    item: Item | None,
    forecast: Forecast | None,
    min_risk_score: float,
    min_up_probability: float,
) -> dict:
    up_probability = forecast.up_probability_14d if forecast else None
    triggered_rules = []
    if (signal.risk_score or 0.0) >= min_risk_score:
        triggered_rules.append("risk_score")
    if signal.risk_level in {"warning", "high"}:
        triggered_rules.append("risk_level")
    if up_probability is not None and up_probability >= min_up_probability:
        triggered_rules.append("up_probability")

    severity = _alert_severity(signal, up_probability, min_up_probability)
    return {
        "item_code": signal.item_code,
        "item_name": item.item_name if item else ITEM_NAMES.get(signal.item_code, signal.item_code),
        "region_code": signal.region_code,
        "region_name": signal.region_name,
        "severity": severity,
        "triggered_rules": triggered_rules,
        "risk": {
            "score": signal.risk_score,
            "level": signal.risk_level,
            "price_effect": signal.price_effect,
            "summary": signal.summary_text,
        },
        "forecast": {
            "direction_14d": forecast.direction_14d if forecast else None,
            "up_probability_14d": up_probability,
            "surge_probability_14d": forecast.surge_probability_14d if forecast else None,
            "confidence": forecast.confidence if forecast else None,
            "model_scope": _card_model_scope(forecast),
        },
    }


def _alert_severity(signal: RegionSignal, up_probability: float | None, min_up_probability: float) -> str:
    risk_score = signal.risk_score or 0.0
    if signal.risk_level == "high" or risk_score >= 85 or (up_probability is not None and up_probability >= max(0.75, min_up_probability)):
        return "critical"
    if signal.risk_level == "warning" or risk_score >= 70:
        return "warning"
    return "watch"


def _alert_rank(alert: dict) -> tuple[int, float, float]:
    severity_rank = {"critical": 3, "warning": 2, "watch": 1}.get(str(alert.get("severity")), 0)
    risk_score = alert.get("risk", {}).get("score") or 0.0
    probability = alert.get("forecast", {}).get("up_probability_14d") or 0.0
    return severity_rank, float(risk_score), float(probability)


@router.get("/api/v1/report/today")
async def get_today_report(db: AsyncSession = Depends(get_db)):
    """일일 리포트 — 기획서 26번 (JSON)
    오늘의 위험 품목 순위 + 지역 + 가격 변동 + 14일 예측 + 자연어 요약
    """
    cached = cache.get("report:today")
    if cached:
        return cached
    today = kst_today()
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

    # 가격 변동 (최근 30일 → 최신 vs 30일전, kamis 기준)
    price_res = await db.execute(
        select(DailyPrice)
        .where(DailyPrice.date >= start_30d, DailyPrice.source == "kamis")
        .order_by(DailyPrice.item_code, DailyPrice.date)
    )
    all_prices = price_res.scalars().all()
    price_by_item: dict[str, list] = {}
    for p in all_prices:
        price_by_item.setdefault(p.item_code, []).append(p)

    def price_change_30d(rows):
        by_date: dict = {}
        for p in rows:
            by_date[p.date] = p
        deduped = sorted(by_date.values(), key=lambda p: p.date)
        if len(deduped) < 2:
            return None
        oldest = deduped[0].wholesale_price
        latest = deduped[-1].wholesale_price
        if not oldest or not latest:
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

    result = {
        "report_date": str(today),
        "generated_at": str(kst_today()),
        "item_count": len(items_report),
        "items": items_report,
    }
    cache.set("report:today", result, ttl=600)  # 10분 캐시
    return result
