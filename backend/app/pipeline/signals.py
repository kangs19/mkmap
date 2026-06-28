"""
RegionSignal 계산기
각 품목·지역 조합의 가격/날씨 기반 위험도 점수(0~100) 산출
"""
import asyncio
import sys, os
from datetime import date, timedelta
from sqlalchemy import select, and_, delete, func

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.database import AsyncSessionLocal
from app.models.item import Item, ItemRegion
from app.models.price import DailyPrice
from app.models.weather import DailyWeather
from app.models.signal import RegionSignal


LOOKBACK = 30  # 기준일 기준 최근 30일 데이터 사용


def _risk_level(score: float) -> str:
    if score >= 70:
        return "high"
    elif score >= 50:
        return "warning"
    elif score >= 30:
        return "caution"
    return "normal"


async def compute_price_signal(db, item_code: str, base_date: date) -> dict:
    """가격 기반 신호: 평년 편차, 변동성, 추세"""
    start = base_date - timedelta(days=LOOKBACK)
    result = await db.execute(
        select(DailyPrice).where(
            and_(
                DailyPrice.item_code == item_code,
                DailyPrice.date >= start,
                DailyPrice.date <= base_date,
            )
        ).order_by(DailyPrice.date)
    )
    rows = result.scalars().all()

    if not rows:
        return {"score": 20, "effect": "neutral", "note": "데이터 없음", "supply_shock": 0.0}

    prices = [r.wholesale_price for r in rows if r.wholesale_price]
    avg_year = [r.avg_year_price for r in rows if r.avg_year_price]

    if not prices:
        return {"score": 20, "effect": "neutral", "note": "가격 데이터 없음", "supply_shock": 0.0}

    latest_price = prices[-1]
    avg_price_30d = sum(prices) / len(prices)

    # 평년 대비 편차
    avg_normal = sum(avg_year) / len(avg_year) if avg_year else avg_price_30d
    deviation = (latest_price - avg_normal) / max(avg_normal, 1)

    # 변동성 (최근 14일 표준편차 / 평균)
    recent = prices[-14:] if len(prices) >= 14 else prices
    mean_r = sum(recent) / len(recent)
    std_r = (sum((p - mean_r) ** 2 for p in recent) / max(len(recent) - 1, 1)) ** 0.5
    vol = std_r / max(mean_r, 1)

    # 단기 추세 (7일 변화율)
    trend = 0.0
    if len(prices) >= 7:
        trend = (prices[-1] - prices[-7]) / max(prices[-7], 1)

    # 점수 계산: 편차 + 변동성 + 추세 가중합
    deviation_score = min(abs(deviation) * 100, 40)  # 최대 40점
    vol_score = min(vol * 200, 30)                   # 최대 30점
    trend_score = min(abs(trend) * 100, 30)          # 최대 30점

    total_score = deviation_score + vol_score + trend_score

    effect = "up" if deviation > 0.05 or trend > 0.05 else ("down" if deviation < -0.05 or trend < -0.05 else "neutral")
    supply_shock = round(-deviation * 0.5, 3)  # 가격 상승 → 공급 부족 근사

    return {
        "score": round(total_score, 1),
        "effect": effect,
        "deviation_pct": round(deviation * 100, 1),
        "volatility_pct": round(vol * 100, 1),
        "trend_7d_pct": round(trend * 100, 1),
        "supply_shock": supply_shock,
    }


async def compute_weather_signal(db, region_code: str, base_date: date) -> dict:
    """날씨 기반 신호: 이상기온, 특보 빈도"""
    start = base_date - timedelta(days=LOOKBACK)
    result = await db.execute(
        select(DailyWeather).where(
            and_(
                DailyWeather.region_code == region_code,
                DailyWeather.date >= start,
                DailyWeather.date <= base_date,
            )
        ).order_by(DailyWeather.date)
    )
    rows = result.scalars().all()

    if not rows:
        return {"score": 0, "alerts": [], "temp_dev_avg": 0, "note": "날씨 데이터 없음"}

    heat_cnt = sum(1 for r in rows if r.heat_alert)
    cold_cnt = sum(1 for r in rows if r.cold_alert)
    rain_cnt = sum(1 for r in rows if r.heavy_rain_alert)

    temp_devs = [(r.avg_temp or 0) - (r.normal_avg_temp or 0) for r in rows]
    temp_dev_avg = sum(temp_devs) / max(len(temp_devs), 1)

    total_precip = sum((r.precipitation or 0) for r in rows)

    # 경보 점수
    alert_score = min((heat_cnt * 4 + cold_cnt * 4 + rain_cnt * 3), 40)
    # 기온 편차 점수
    temp_score = min(abs(temp_dev_avg) * 3, 30)
    # 강수 점수 (30일 합계 기준)
    precip_score = min(total_precip / 20, 30)

    total_score = alert_score + temp_score + precip_score

    alerts = []
    if heat_cnt > 0:
        alerts.append(f"폭염 {heat_cnt}일")
    if cold_cnt > 0:
        alerts.append(f"한파 {cold_cnt}일")
    if rain_cnt > 0:
        alerts.append(f"호우 {rain_cnt}일")

    return {
        "score": round(total_score, 1),
        "alerts": alerts,
        "temp_dev_avg": round(temp_dev_avg, 1),
        "total_precip_30d": round(total_precip, 1),
        "heat_days": heat_cnt,
        "cold_days": cold_cnt,
        "rain_days": rain_cnt,
    }


async def compute_region_signals(item_code: str, base_date: date = None, verbose=True):
    """품목 전체 지역의 RegionSignal 계산 및 저장"""
    if base_date is None:
        base_date = date.today()

    if verbose:
        print(f"\n[RegionSignal] {item_code} / {base_date}")

    async with AsyncSessionLocal() as db:
        # 현재 계절 판단
        month = base_date.month
        if month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        elif month in [9, 10, 11]:
            season = "autumn"
        else:
            season = "winter"

        # 해당 품목·계절 지역 목록
        r = await db.execute(
            select(ItemRegion).where(
                and_(
                    ItemRegion.item_code == item_code,
                    ItemRegion.season == season,
                )
            )
        )
        regions = r.scalars().all()

        if not regions:
            if verbose:
                print(f"  지역 데이터 없음 (계절: {season})")
            return []

        # 가격 신호 한 번만 계산 (전국 공통)
        price_sig = await compute_price_signal(db, item_code, base_date)

        results = []
        for region in regions:
            weather_sig = await compute_weather_signal(db, region.region_code, base_date)

            # 종합 점수: 가격 60% + 날씨 40%
            combined_score = price_sig["score"] * 0.6 + weather_sig["score"] * 0.4
            combined_score = min(combined_score, 100)

            risk_lvl = _risk_level(combined_score)

            summary_parts = []
            if price_sig["effect"] == "up":
                summary_parts.append(f"가격 평년 대비 {price_sig['deviation_pct']:+.1f}%")
            elif price_sig["effect"] == "down":
                summary_parts.append(f"가격 평년 대비 {price_sig['deviation_pct']:+.1f}%")
            if weather_sig["alerts"]:
                summary_parts.append("기상특보: " + ", ".join(weather_sig["alerts"]))
            summary_text = " | ".join(summary_parts) if summary_parts else "특이사항 없음"

            # 기존 신호 삭제 후 재삽입
            await db.execute(
                delete(RegionSignal).where(
                    and_(
                        RegionSignal.item_code == item_code,
                        RegionSignal.region_code == region.region_code,
                        RegionSignal.date == base_date,
                    )
                )
            )

            signal = RegionSignal(
                item_code=item_code,
                region_code=region.region_code,
                region_name=region.region_name,
                date=base_date,
                risk_score=round(combined_score, 1),
                risk_level=risk_lvl,
                supply_shock=price_sig.get("supply_shock", 0.0),
                price_effect=price_sig["effect"],
                weather_summary={
                    "alerts": weather_sig["alerts"],
                    "temp_dev_avg": weather_sig["temp_dev_avg"],
                    "total_precip_30d": weather_sig.get("total_precip_30d", 0),
                    "heat_days": weather_sig.get("heat_days", 0),
                    "cold_days": weather_sig.get("cold_days", 0),
                    "rain_days": weather_sig.get("rain_days", 0),
                },
                market_summary={
                    "deviation_pct": price_sig.get("deviation_pct", 0),
                    "volatility_pct": price_sig.get("volatility_pct", 0),
                    "trend_7d_pct": price_sig.get("trend_7d_pct", 0),
                },
                summary_text=summary_text,
            )
            db.add(signal)
            results.append({
                "region_code": region.region_code,
                "region_name": region.region_name,
                "risk_score": round(combined_score, 1),
                "risk_level": risk_lvl,
            })

            if verbose:
                print(f"  {region.region_name} ({region.region_code}): "
                      f"위험도 {combined_score:.0f} [{risk_lvl}]")

        await db.commit()
        return results


async def run_all_signals(base_date: date = None):
    """모든 활성 품목의 RegionSignal 계산"""
    if base_date is None:
        base_date = date.today()

    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Item).where(Item.is_active == True))
        items = r.scalars().all()

    all_results = {}
    for item in items:
        try:
            results = await compute_region_signals(item.item_code, base_date)
            all_results[item.item_code] = results
        except Exception as e:
            print(f"  오류 ({item.item_code}): {e}")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_all_signals())
