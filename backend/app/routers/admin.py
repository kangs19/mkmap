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
    _=Depends(check_admin),
):
    """수동 파이프라인 실행 — 특정 품목 또는 전체 (기획서 17번)"""
    import asyncio
    from app.pipeline.batch import run_batch
    from app.pipeline.runner import run_pipeline

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
    _=Depends(check_admin),
):
    """수동 데이터 수집 실행 — kamis | kma | kosis | all"""
    from app.collectors.sync import run_full_sync, daily_sync
    try:
        result = await daily_sync()
        return {"status": "ok", "source": source, "result": result}
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
    from app.scheduler import scheduler

    price_count = (await db.execute(select(func.count()).select_from(DailyPrice))).scalar()
    weather_count = (await db.execute(select(func.count()).select_from(DailyWeather))).scalar()
    signal_count = (await db.execute(select(func.count()).select_from(RegionSignal))).scalar()

    latest_signal = (await db.execute(
        select(Forecast.base_date).order_by(desc(Forecast.base_date)).limit(1)
    )).scalar()

    return {
        "date": str(date.today()),
        "db": {
            "daily_prices": price_count,
            "daily_weather": weather_count,
            "region_signals": signal_count,
            "latest_forecast": str(latest_signal) if latest_signal else None,
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()],
        },
    }


@router.get("/debug/kamis")
async def debug_kamis(_=Depends(check_admin)):
    """KAMIS API 직접 테스트 — 실제 응답 반환"""
    import httpx
    from app.config import get_settings
    from datetime import date, timedelta

    settings = get_settings()
    end = date.today()
    start = end - timedelta(days=3)

    params = {
        "action": "dailySalesList",
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": start.strftime("%Y-%m-%d"),
        "p_endday": end.strftime("%Y-%m-%d"),
        "p_itemcategorycode": "100",
        "p_itemcode": "112",
        "p_kindcode": "01",
        "p_productrankcode": "04",
        "p_countrycode": "1101",
        "p_convert_kg_yn": "N",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://www.kamis.or.kr/service/price/xml.do", params=params)
        try:
            resp_data = r.json()
        except Exception:
            resp_data = r.text
        return {
            "http_status": r.status_code,
            "response": resp_data,
            "api_key_set": bool(settings.kamis_api_key),
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
