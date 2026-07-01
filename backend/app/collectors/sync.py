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
from app.models.production import CropProduction
from app.models.market import DailyMarket
from app.collectors.kamis import ITEM_CODE_MAP
from app.collectors.kamis_market import fetch_market_volume
from app.collectors.kma import fetch_forecast, REGION_GRID
from app.collectors.kma_agri import fetch_crop_weather, CROP_REGION_MAP
from app.collectors.kosis import fetch_all_crops_production
from app.config import get_settings

import logging
log = logging.getLogger(__name__)

ALL_ITEMS = list(ITEM_CODE_MAP.keys())
ALL_REGIONS = list(REGION_GRID.keys())


async def sync_prices(days_back: int = 7) -> dict:
    """KAMIS periodProductList 기반 날짜별 가격 동기화 (httpx, SSL 우회).

    dailySalesList는 날짜 파라미터를 무시해 change_30d_pct=0.0 버그 발생.
    periodProductList + httpx(verify=False)로 Railway SSL 우회.
    """
    settings = get_settings()
    if not settings.kamis_api_key:
        log.warning("KAMIS_API_KEY 없음 — 가격 동기화 스킵")
        return {"skipped": True}

    from app.collectors.kamis import fetch_period_prices
    from app.timezone import kst_today

    end_date = kst_today()
    start_date = end_date - timedelta(days=days_back)
    saved = 0
    failed_items: list[str] = []

    for item_code in ALL_ITEMS:
        try:
            rows = await fetch_period_prices(item_code, start_date, end_date)
        except Exception as e:
            log.warning(f"KAMIS 가격 수집 실패: {item_code} — {e}")
            failed_items.append(item_code)
            continue

        if not rows:
            log.info(f"KAMIS 가격 없음: {item_code}")
            continue

        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(DailyPrice).values([
                    {
                        "item_code": row["item_code"],
                        "date": row["date"],
                        "market": row.get("market", ""),
                        "grade": row.get("grade", ""),
                        "wholesale_price": row["wholesale_price"],
                        "retail_price": row.get("retail_price"),
                        "source": "kamis",
                    }
                    for row in rows
                    if row.get("wholesale_price") and row["wholesale_price"] > 0
                ]).on_conflict_do_update(
                    index_elements=["item_code", "date", "source"],
                    set_={
                        "wholesale_price": pg_insert(DailyPrice).excluded.wholesale_price,
                        "retail_price": pg_insert(DailyPrice).excluded.retail_price,
                    }
                )
                result = await db.execute(stmt)
                await db.commit()
                saved += result.rowcount or len(rows)
            except Exception:
                # SQLite 환경 폴백 (로컬 개발)
                await db.rollback()
                for row in rows:
                    if not row.get("wholesale_price") or row["wholesale_price"] <= 0:
                        continue
                    existing = await db.execute(
                        select(DailyPrice).where(
                            DailyPrice.item_code == row["item_code"],
                            DailyPrice.date == row["date"],
                            DailyPrice.source == "kamis",
                        )
                    )
                    if existing.scalars().first():
                        continue
                    db.add(DailyPrice(
                        item_code=row["item_code"],
                        date=row["date"],
                        market=row.get("market", ""),
                        grade=row.get("grade", ""),
                        wholesale_price=row["wholesale_price"],
                        retail_price=row.get("retail_price"),
                        source="kamis",
                    ))
                    saved += 1
                await db.commit()

        log.info(f"KAMIS 가격 저장: {item_code} {len(rows)}건")
        await asyncio.sleep(0.5)

    return {"saved": saved, "items": ALL_ITEMS, "failed_items": failed_items}


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
                if existing.scalars().first():
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


async def sync_kosis(years: int = 3) -> dict:
    """KOSIS 생산통계 동기화 — crop_productions 테이블에 저장"""
    settings = get_settings()
    if not settings.kosis_api_key:
        log.warning("KOSIS_API_KEY 없음 — 생산통계 동기화 스킵")
        return {"skipped": True}
    try:
        all_data = await fetch_all_crops_production(years=years)
        saved = 0
        for item_code, rows in all_data.items():
            if not rows:
                continue
            async with AsyncSessionLocal() as db:
                for row in rows:
                    existing = await db.execute(
                        select(CropProduction).where(
                            CropProduction.item_code == row["item_code"],
                            CropProduction.year == row["year"],
                        )
                    )
                    if existing.scalars().first():
                        continue
                    yield_per_ha = None
                    if row.get("area_ha") and row.get("production_ton"):
                        yield_per_ha = round(row["production_ton"] / row["area_ha"], 2)
                    db.add(CropProduction(
                        item_code=row["item_code"],
                        year=row["year"],
                        area_ha=row.get("area_ha"),
                        production_ton=row.get("production_ton"),
                        yield_per_ha=yield_per_ha,
                        source="kosis",
                    ))
                    saved += 1
                await db.commit()
        log.info(f"KOSIS 생산통계 저장: {saved}건")
        return {"saved": saved, "items": list(all_data.keys())}
    except Exception as e:
        log.warning(f"KOSIS 동기화 실패: {e}")
        return {"error": str(e)}


async def sync_market_volume(days_back: int = 7) -> dict:
    """KAMIS 도매시장 거래량 동기화 — daily_market 테이블"""
    settings = get_settings()
    if not settings.kamis_api_key:
        log.warning("KAMIS_API_KEY 없음 — 거래량 동기화 스킵")
        return {"skipped": True}

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)
    saved = 0

    for item_code in ALL_ITEMS:
        rows = await fetch_market_volume(item_code, start_date, end_date)
        if not rows:
            log.info(f"KAMIS 거래량 없음: {item_code}")
            continue

        async with AsyncSessionLocal() as db:
            for row in rows:
                existing = await db.execute(
                    select(DailyMarket).where(
                        DailyMarket.item_code == row["item_code"],
                        DailyMarket.date == row["date"],
                        DailyMarket.source == "kamis",
                    )
                )
                if existing.scalars().first():
                    continue
                db.add(DailyMarket(**row))
                saved += 1
            await db.commit()
        await asyncio.sleep(0.5)

    return {"saved": saved, "items": ALL_ITEMS}


async def run_full_sync(days_back: int = 30) -> dict:
    """초기 구동 시 전체 동기화 (최근 N일)"""
    log.info(f"전체 실데이터 동기화 시작 (최근 {days_back}일)")
    price_result  = await sync_prices(days_back=days_back)
    weather_result = await sync_weather(days_back=min(days_back, 3))
    market_result = await sync_market_volume(days_back=days_back)
    kosis_result  = await sync_kosis(years=3)
    log.info(f"동기화 완료: 가격={price_result}, 기상={weather_result}, 거래량={market_result}, KOSIS={kosis_result}")
    return {"prices": price_result, "weather": weather_result,
            "market": market_result, "kosis": kosis_result}


async def sync_agri_weather(days_back: int = 1) -> dict:
    """농업주산지 상세날씨 동기화 (kma_agri — 403이면 자동 스킵)"""
    saved = 0
    end_date = date.today()

    for item_code in CROP_REGION_MAP:
        for offset in range(days_back, -1, -1):
            target = end_date - timedelta(days=offset)
            rows = await fetch_crop_weather(item_code, target)
            if not rows:
                continue
            async with AsyncSessionLocal() as db:
                for row in rows:
                    existing = await db.execute(
                        select(DailyWeather).where(
                            DailyWeather.region_code == row["region_code"],
                            DailyWeather.date == row["date"],
                            DailyWeather.source == "kma_agri",
                        )
                    )
                    if existing.scalars().first():
                        continue
                    db.add(DailyWeather(**row))
                    saved += 1
                await db.commit()
            await asyncio.sleep(0.3)

    return {"saved": saved}


async def daily_sync() -> dict:
    """스케줄러용 일별 동기화"""
    price_result  = await sync_prices(days_back=3)
    weather_result = await sync_weather(days_back=1)
    agri_result   = await sync_agri_weather(days_back=1)
    market_result = await sync_market_volume(days_back=3)
    return {"prices": price_result, "weather": weather_result,
            "agri_weather": agri_result, "market": market_result}
