"""
관리자 전용 엔드포인트 — API 키 발급·조회·비활성화
X-Admin-Key 헤더로 보호
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.api_key import ApiKey, ApiUsageLog
from app.auth import generate_key, hash_key
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_KEY = os.environ.get("ADMIN_KEY", "agri-admin-dev-key-change-in-prod")


def check_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="관리자 키가 올바르지 않습니다.")


@router.post("/keys")
async def create_api_key(
    name: str,
    plan: str = "free",
    rate_limit: int = 100,
    expires_days: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """API 키 발급"""
    raw = generate_key()
    key_hash = hash_key(raw)
    expires_at = datetime.now() + timedelta(days=expires_days) if expires_days else None

    db.add(ApiKey(
        key_hash=key_hash,
        name=name,
        plan=plan,
        rate_limit=rate_limit,
        expires_at=expires_at,
    ))
    await db.commit()

    return {
        "api_key": raw,           # 한 번만 노출 — DB엔 해시만 저장
        "name": name,
        "plan": plan,
        "rate_limit": rate_limit,
        "expires_at": str(expires_at) if expires_at else None,
        "warning": "이 키는 다시 조회할 수 없습니다. 지금 바로 저장하세요.",
    }


@router.get("/keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """발급된 키 목록 (해시만 표시)"""
    result = await db.execute(
        select(ApiKey).order_by(desc(ApiKey.created_at))
    )
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "plan": k.plan,
            "is_active": k.is_active,
            "rate_limit": k.rate_limit,
            "total_calls": k.total_calls,
            "last_used": str(k.last_used) if k.last_used else None,
            "expires_at": str(k.expires_at) if k.expires_at else None,
            "created_at": str(k.created_at),
            "key_prefix": "agri_***",
        }
        for k in keys
    ]


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """키 비활성화"""
    key = await db.get(ApiKey, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")
    key.is_active = False
    await db.commit()
    return {"message": f"키 '{key.name}' 비활성화 완료"}


@router.get("/usage")
async def get_usage_stats(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """최근 API 사용 로그"""
    result = await db.execute(
        select(ApiUsageLog)
        .order_by(desc(ApiUsageLog.called_at))
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "endpoint": l.endpoint,
            "method": l.method,
            "status": l.status,
            "latency_ms": l.latency_ms,
            "called_at": str(l.called_at),
        }
        for l in logs
    ]


@router.get("/health")
async def admin_health(_=Depends(check_admin)):
    from datetime import date
    from app.scheduler import scheduler
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return {
        "status": "ok",
        "date": str(date.today()),
        "scheduler_running": scheduler.running,
        "scheduled_jobs": jobs,
    }


@router.post("/pipeline/run")
async def manual_run_pipeline(
    item_code: Optional[str] = None,
    background: bool = True,
    _=Depends(check_admin),
):
    """수동 파이프라인 실행 — background=True(기본): 즉시 202 반환 후 백그라운드 실행"""
    import asyncio
    from app.pipeline.batch import run_batch
    from app.pipeline.runner import run_pipeline

    async def _run_bg():
        try:
            if item_code:
                await run_pipeline(item_code=item_code, verbose=True)
            else:
                await run_batch(verbose=True)
        except Exception as e:
            print(f"[pipeline bg error] {e}")

    if background:
        asyncio.create_task(_run_bg())
        return {
            "status": "started",
            "item_code": item_code or "all",
            "message": "백그라운드에서 실행 중. /admin/status 로 결과 확인"
        }

    try:
        if item_code:
            result = await run_pipeline(item_code=item_code, verbose=True)
            return {"status": "ok", "item_code": item_code, "result": result}
        else:
            results = await run_batch(verbose=False)
            ok = sum(1 for v in results.values() if v.get("status") == "ok")
            return {
                "status": "ok",
                "total": len(results),
                "success": ok,
                "results": {
                    k: {"status": v.get("status"), "direction": v.get("forecast", {}).get("direction_14d")}
                    for k, v in results.items()
                },
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/run")
async def manual_run_sync(
    source: str = "all",
    days_back: int = 7,
    include_kosis: bool = True,
    background: bool = True,
    _=Depends(check_admin),
):
    """수동 데이터 수집 — background=True(기본): 202 즉시 반환 후 백그라운드 실행"""
    import asyncio
    from app.collectors.sync import sync_prices, sync_weather, sync_kosis, sync_market_volume

    async def _run():
        try:
            if source in ("all", "kamis"):
                await sync_prices(days_back=days_back)
            if source in ("all", "kma"):
                await sync_weather(days_back=min(days_back, 14))
            if source in ("all", "kamis"):
                await sync_market_volume(days_back=days_back)
            if include_kosis and source in ("all", "kosis"):
                await sync_kosis(years=3)
        except Exception as e:
            print(f"[sync background error] {e}")

    if background:
        asyncio.create_task(_run())
        return {
            "status": "started",
            "source": source,
            "days_back": days_back,
            "message": "백그라운드에서 실행 중. /admin/status 로 진행 확인"
        }
    else:
        try:
            result = {}
            if source in ("all", "kamis"):
                result["prices"] = await sync_prices(days_back=days_back)
            if source in ("all", "kma"):
                result["weather"] = await sync_weather(days_back=min(days_back, 14))
            if source in ("all", "kamis"):
                result["market"] = await sync_market_volume(days_back=days_back)
            if include_kosis and source in ("all", "kosis"):
                result["kosis"] = await sync_kosis(years=3)
            return {"status": "ok", "source": source, "days_back": days_back, "result": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def admin_status(
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """시스템 전체 상태 — DB 레코드 수, 최신 예측일, 스케줄러"""
    from datetime import date
    from sqlalchemy import func
    from app.models.price import DailyPrice
    from app.models.weather import DailyWeather
    from app.models.signal import RegionSignal
    from app.models.forecast import Forecast
    from app.models.item import Item, ItemRegion
    from app.scheduler import scheduler

    price_count = (await db.execute(select(func.count()).select_from(DailyPrice))).scalar()
    weather_count = (await db.execute(select(func.count()).select_from(DailyWeather))).scalar()
    signal_count = (await db.execute(select(func.count()).select_from(RegionSignal))).scalar()
    item_count = (await db.execute(select(func.count()).select_from(Item))).scalar()

    # 시드 자동 실행 (items 테이블 비어있으면)
    seed_result = None
    if item_count == 0:
        try:
            ITEMS = [
                {"item_code": "cabbage",     "item_name": "배추", "category": "채소류", "wholesale_unit": "10kg",  "is_active": True},
                {"item_code": "radish",      "item_name": "무",   "category": "채소류", "wholesale_unit": "20kg",  "is_active": True},
                {"item_code": "onion",       "item_name": "양파", "category": "채소류", "wholesale_unit": "20kg",  "is_active": True},
                {"item_code": "green_onion", "item_name": "대파", "category": "채소류", "wholesale_unit": "1kg",   "is_active": True},
                {"item_code": "garlic",      "item_name": "마늘", "category": "채소류", "wholesale_unit": "10kg",  "is_active": True},
            ]
            for item_data in ITEMS:
                db.add(Item(**item_data))
            await db.commit()
            item_count = 5
            seed_result = "auto-seeded"
        except Exception as e:
            seed_result = f"seed-error: {e}"

    latest_signal = (await db.execute(
        select(Forecast.base_date).order_by(desc(Forecast.base_date)).limit(1)
    )).scalar()

    return {
        "date": str(date.today()),
        "db": {
            "items": item_count,
            "daily_prices": price_count,
            "daily_weather": weather_count,
            "region_signals": signal_count,
            "latest_forecast": str(latest_signal) if latest_signal else None,
            "seed_result": seed_result,
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()],
        },
    }


@router.post("/meta/build")
async def build_meta(
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """품목별 메타데이터 빌드 — KAMIS/KOSIS/KMA 실데이터 피처 집계"""
    from app.collectors.meta_builder import build_all_meta
    try:
        results = await build_all_meta(db)
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/kamis")
async def debug_kamis(days_ago: int = 0, _=Depends(check_admin)):
    """KAMIS API 직접 테스트 — days_ago=0이면 오늘, days_ago=30이면 30일 전"""
    import httpx
    from app.config import get_settings
    from datetime import date, timedelta

    settings = get_settings()
    target = date.today() - timedelta(days=days_ago)

    params = {
        "action": "dailySalesList",
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": target.strftime("%Y-%m-%d"),
        "p_endday": target.strftime("%Y-%m-%d"),
        "p_countrycode": "1101",
        "p_convert_kg_yn": "N",
    }
    TARGETS = {"28": "배추", "64": "무", "117": "양파", "122": "대파", "1003": "마늘"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://www.kamis.or.kr/service/price/xml.do", params=params)
        data = r.json()
        # 우리 5개 품목만 필터
        filtered = [
            {
                "productno": str(row.get("productno","")),
                "name": TARGETS.get(str(row.get("productno","")), "?"),
                "cls": row.get("product_cls_code",""),
                "dpr1": row.get("dpr1",""),
            }
            for row in data.get("price", [])
            if str(row.get("productno","")) in TARGETS and row.get("product_cls_code") == "02"
        ]
        return {
            "target_date": str(target),
            "http_status": r.status_code,
            "our_items": filtered,
            "total_rows": len(data.get("price", [])),
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}


@router.get("/debug/price-counts")
async def debug_price_counts(db: AsyncSession = Depends(get_db), _=Depends(check_admin)):
    """품목별 DB 가격 레코드 수 확인"""
    from sqlalchemy import func
    from app.models.price import DailyPrice
    result = await db.execute(
        select(DailyPrice.item_code, func.count().label("cnt"), func.min(DailyPrice.date).label("min_date"), func.max(DailyPrice.date).label("max_date"))
        .group_by(DailyPrice.item_code)
    )
    return [{"item": r.item_code, "count": r.cnt, "min": str(r.min_date), "max": str(r.max_date)} for r in result.all()]


@router.get("/debug/fetch-prices")
async def debug_fetch_prices(_=Depends(check_admin)):
    """fetch_all_prices_for_date(today) 실제 반환값 확인"""
    from datetime import date
    from app.collectors.kamis import fetch_all_prices_for_date
    result = await fetch_all_prices_for_date(date.today())
    return {
        "date": str(date.today()),
        "items_found": list(result.keys()),
        "data": {k: {"price": v.get("wholesale_price")} for k, v in result.items()},
    }


@router.post("/init-data")
async def run_seed(db: AsyncSession = Depends(get_db), _=Depends(check_admin)):
    """Item 시드 수동 실행 — 재배포 후 빈 items 테이블 복구"""
    from app.models.item import Item, ItemRegion

    ITEMS = [
        {"item_code": "cabbage",     "item_name": "배추", "category": "채소류", "wholesale_unit": "10kg", "is_active": True},
        {"item_code": "radish",      "item_name": "무",   "category": "채소류", "wholesale_unit": "20kg", "is_active": True},
        {"item_code": "onion",       "item_name": "양파", "category": "채소류", "wholesale_unit": "20kg", "is_active": True},
        {"item_code": "green_onion", "item_name": "대파", "category": "채소류", "wholesale_unit": "1kg",  "is_active": True},
        {"item_code": "garlic",      "item_name": "마늘", "category": "채소류", "wholesale_unit": "10kg", "is_active": True},
    ]
    REGIONS = [
        ("cabbage",     "KR-46", "전남", "해남",  True),
        ("cabbage",     "KR-42", "강원", "고랭지", False),
        ("radish",      "KR-46", "전남", "무안",  True),
        ("radish",      "KR-42", "강원", "고랭지", False),
        ("onion",       "KR-46", "전남", "무안",  True),
        ("onion",       "KR-48", "경남", "창원",  False),
        ("green_onion", "KR-46", "전남", "진도",  True),
        ("green_onion", "KR-41", "경기", "수원",  False),
        ("garlic",      "KR-47", "경북", "의성",  True),
        ("garlic",      "KR-46", "전남", "해남",  False),
    ]
    try:
        added_items = 0
        for item_data in ITEMS:
            existing = await db.execute(select(Item).where(Item.item_code == item_data["item_code"]))
            if existing.scalar_one_or_none() is None:
                db.add(Item(**item_data))
                added_items += 1

        for ic, rc, rn, sub, primary in REGIONS:
            existing = await db.execute(
                select(ItemRegion).where(ItemRegion.item_code == ic, ItemRegion.region_code == rc)
            )
            if existing.scalar_one_or_none() is None:
                db.add(ItemRegion(item_code=ic, region_code=rc, region_name=rn, sub_region=sub, is_primary=primary))

        await db.commit()
        return {"status": "ok", "added_items": added_items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
