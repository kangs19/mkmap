"""
실데이터 동기화 — KAMIS 가격 + KMA 기상 → DB 저장
스케줄러(매일 06:00)에서 호출
"""
import asyncio
from datetime import date, timedelta
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.price import DailyPrice
from app.models.weather import DailyWeather
from app.collectors.kamis import fetch_price_range, ITEM_CODE_MAP
from app.collectors.kma import fetch_forecast, REGION_GRID
from app.config import get_settings

import logging
log = logging.getLogger(__name__)

ALL_ITEMS = list(ITEM_CODE_MAP.keys())
ALL_REGIONS = list(REGION_GRID.keys())


async def sync_prices(days_back: int = 7) -> dict:
    """KAMIS 가격 최근 N일 동기화"""
    settings = get_settings()
    if not settings.kamis_api_key:
        log.warning("KAMIS_API_KEY 없음 — 가격 동기화 스킵")
        return {"skipped": True}

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    saved = 0

    for item_code in ALL_ITEMS:
        rows = await fetch_price_range(item_code, start_date, end_date)
        if not rows:
            log.info(f"KAMIS 가격 없음: {item_code}")
            continue

        async with AsyncSessionLocal() as db:
            for row in rows:
                # 이미 있으면 upsert (날짜+품목+source 기준)
                existing = await db.execute(
                    select(DailyPrice).where(
                        DailyPrice.item_code == row["item_code"],
                        DailyPrice.date == row["date"],
                        DailyPrice.source == "kamis",
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                db.add(DailyPrice(**row))
                saved += 1
            await db.commit()

        log.info(f"KAMIS 가격 저장: {item_code} {len(rows)}건")
        await asyncio.sleep(0.5)  # API 과부하 방지

    return {"saved": saved, "items": ALL_ITEMS}


async def sync_weather(days_back: int = 3) -> dict:
    """KMA 기상예보 최근 N일 동기화"""
    settings = get_settings()
    if not settings.kma_api_key:
        log.warning("KMA_API_KEY 없음 — 기상 동기화 스킵")
        return {"skipped": True}

    end_date = date.today()
    saved = 0

    for region_code in ALL_REGIONS:
        for offset in range(days_back, -1, -1):
            target = end_date - timedelta(days=offset)

            async with AsyncSessionLocal() as db:
                existing = await db.execute(
                    select(DailyWeather).where(
                        DailyWeather.region_code == region_code,
                        DailyWeather.date == target,
                        DailyWeather.source.in_(["kma_forecast", "kma_ultra"]),
                    )
                )
                if existing.scalar_one_or_none():
                    continue

            row = await fetch_forecast(region_code, target)
            if not row:
                continue

            async with AsyncSessionLocal() as db:
                db.add(DailyWeather(**row))
                await db.commit()
                saved += 1

            await asyncio.sleep(0.3)

    return {"saved": saved, "regions": ALL_REGIONS}


async def run_full_sync(days_back: int = 30) -> dict:
    """초기 구동 시 전체 동기화 (최근 N일)"""
    log.info(f"전체 실데이터 동기화 시작 (최근 {days_back}일)")
    price_result = await sync_prices(days_back=days_back)
    weather_result = await sync_weather(days_back=min(days_back, 3))
    log.info(f"동기화 완료: 가격={price_result}, 기상={weather_result}")
    return {"prices": price_result, "weather": weather_result}


async def daily_sync() -> dict:
    """스케줄러용 일별 동기화"""
    price_result = await sync_prices(days_back=3)
    weather_result = await sync_weather(days_back=1)
    return {"prices": price_result, "weather": weather_result}
