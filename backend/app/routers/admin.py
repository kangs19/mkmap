"""
관리자 전용 엔드포인트 — API 키 발급·조회·비활성화
X-Admin-Key 헤더로 보호
"""
import os
import sys
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.api_key import ApiKey, ApiUsageLog
from app.auth import generate_key, hash_key
from datetime import timedelta
from typing import Optional
from app.timezone import kst_now, kst_today

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
REPO_ROOT = Path(__file__).resolve().parents[3]
DIAGNOSTICS_ROOT = REPO_ROOT / "data" / "diagnostics"


def check_admin(x_admin_key: str = Header(...)):
    if not ADMIN_KEY:
        raise HTTPException(status_code=503, detail="ADMIN_KEY is not configured.")
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
    expires_at = kst_now().replace(tzinfo=None) + timedelta(days=expires_days) if expires_days else None

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
    from app.scheduler import scheduler
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return {
        "status": "ok",
        "date": str(kst_today()),
        "scheduler_running": scheduler.running,
        "scheduled_jobs": jobs,
    }


import asyncio as _asyncio
_pipeline_sem = _asyncio.Semaphore(1)  # 동시 파이프라인 1개 제한
_meta_pipeline_status = {
    "running": False,
    "last_status": None,
    "last_started_at": None,
    "last_finished_at": None,
    "last_date": None,
    "last_output_tail": [],
    "last_error": None,
}


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[3]


def _model_evaluation_path(target_date: str):
    from pathlib import Path
    stamp = target_date.replace("-", "")
    return Path(_repo_root()) / "data" / "model" / f"price_baseline_model_{stamp}_evaluation.json"


def _freshness_status(lag_days: int | None, warn_after_days: int) -> str:
    if lag_days is None:
        return "missing"
    if lag_days <= warn_after_days:
        return "fresh"
    if lag_days <= warn_after_days + 2:
        return "stale"
    return "missing"


def _freshness_payload(latest_date, today, warn_after_days: int) -> dict:
    latest_text = str(latest_date) if latest_date else None
    lag_days = (today - latest_date).days if latest_date else None
    return {
        "latest_date": latest_text,
        "lag_days": lag_days,
        "status": _freshness_status(lag_days, warn_after_days),
        "warn_after_days": warn_after_days,
    }


def _latest_weather_collection_summary(today) -> dict | None:
    paths = sorted(
        (REPO_ROOT / "data" / "features").glob("*/kma_crop_weather_collection_summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not paths:
        return None

    path = paths[0]
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "summary_path": str(path.relative_to(REPO_ROOT)),
            "error": str(exc),
        }
    if not isinstance(rows, list):
        return {
            "status": "error",
            "summary_path": str(path.relative_to(REPO_ROOT)),
            "error": "summary payload is not a list",
        }

    target_dates = sorted({str(row.get("target_date")) for row in rows if isinstance(row, dict) and row.get("target_date")})
    used_dates = sorted({str(row.get("used_date")) for row in rows if isinstance(row, dict) and row.get("used_date")})
    feature_count = sum(int(row.get("feature_count") or 0) for row in rows if isinstance(row, dict))
    error_count = sum(int(row.get("error_count") or 0) for row in rows if isinstance(row, dict))
    item_count = len(rows)
    latest_target = target_dates[-1] if target_dates else None
    latest_used = used_dates[-1] if used_dates else None

    if feature_count > 0 and latest_used and latest_target and latest_used < latest_target:
        status = "fallback"
    elif feature_count > 0:
        status = "ok"
    elif latest_target == str(today) and error_count > 0:
        status = "provider_delay"
    elif error_count > 0:
        status = "no_data"
    else:
        status = "missing"

    return {
        "status": status,
        "summary_path": str(path.relative_to(REPO_ROOT)),
        "item_count": item_count,
        "feature_count": feature_count,
        "error_count": error_count,
        "target_date": latest_target,
        "used_date": latest_used,
    }


def _weather_freshness_payload(latest_date, today, warn_after_days: int) -> dict:
    payload = _freshness_payload(latest_date, today, warn_after_days)
    collection = _latest_weather_collection_summary(today)
    if collection:
        payload["collection"] = collection
        if payload["status"] == "missing" and collection.get("status") in {"provider_delay", "fallback", "no_data"}:
            payload["status"] = collection["status"]
    return payload


def _latest_live_api_diagnostics() -> dict:
    paths = sorted(
        DIAGNOSTICS_ROOT.glob("*/live_api_diagnostics.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not paths:
        return {
            "status": "missing",
            "latest_report": None,
            "summary": {},
            "results": [],
            "untested_services": [],
        }

    path = paths[0]
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "latest_report": str(path.relative_to(REPO_ROOT)),
            "error": str(exc),
            "summary": {},
            "results": [],
            "untested_services": [],
        }

    return {
        "status": "ok" if report.get("ok") else "attention",
        "latest_report": str(path.relative_to(REPO_ROOT)),
        "generated_at": report.get("generated_at"),
        "date": report.get("date"),
        "item": report.get("item"),
        "summary": report.get("summary") or {},
        "results": [
            _compact_diagnostic_result(result)
            for result in report.get("results", [])
        ],
        "untested_services": [
            _compact_diagnostic_result(result)
            for result in report.get("untested_services", [])
        ],
    }


def _compact_diagnostic_result(result: dict) -> dict:
    service = result.get("service") if isinstance(result.get("service"), dict) else {}
    return {
        "code": result.get("code") or result.get("service_code"),
        "service_code": result.get("service_code"),
        "engine_role": result.get("engine_role"),
        "status": result.get("status"),
        "ok": result.get("ok"),
        "reason": result.get("reason"),
        "next_action": result.get("next_action"),
        "metrics": result.get("metrics") or {},
        "provider": service.get("provider"),
        "display_name": service.get("display_name"),
        "configured": service.get("configured"),
        "missing_env": service.get("missing_env") or [],
        "operation": service.get("operation"),
    }


async def _run_meta_pipeline_process(
    target_date: str | None,
    skip_collect: bool,
    weather_lookback_days: int,
    weather_max_requests_per_item: int = 16,
    weather_request_timeout_seconds: int = 8,
) -> dict:
    from app import cache

    pipeline_date = target_date or kst_today().isoformat()
    cmd = [
        sys.executable,
        "scripts/run_meta_pipeline.py",
        "--date",
        pipeline_date,
        "--weather-lookback-days",
        str(weather_lookback_days),
        "--weather-max-requests-per-item",
        str(weather_max_requests_per_item),
        "--weather-request-timeout-seconds",
        str(weather_request_timeout_seconds),
    ]
    if skip_collect:
        cmd.append("--skip-collect")

    _meta_pipeline_status.update(
        {
            "running": True,
            "last_status": "running",
            "last_started_at": kst_now().isoformat(timespec="seconds"),
            "last_finished_at": None,
            "last_date": pipeline_date,
            "last_output_tail": [],
            "last_error": None,
        }
    )

    try:
        process = await _asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_repo_root()),
            stdout=_asyncio.subprocess.PIPE,
            stderr=_asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        output_lines: list[str] = []
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(text)
            _meta_pipeline_status["last_output_tail"] = output_lines[-80:]

        return_code = await process.wait()
        finished_at = kst_now().isoformat(timespec="seconds")
        if return_code == 0:
            cache.clear_prefix("signals:")
            cache.clear_prefix("report:")
            _meta_pipeline_status.update(
                {
                    "running": False,
                    "last_status": "ok",
                    "last_finished_at": finished_at,
                    "last_error": None,
                    "last_output_tail": output_lines[-80:],
                }
            )
        else:
            _meta_pipeline_status.update(
                {
                    "running": False,
                    "last_status": "error",
                    "last_finished_at": finished_at,
                    "last_error": f"process exited with code {return_code}",
                    "last_output_tail": output_lines[-80:],
                }
            )
        return dict(_meta_pipeline_status)
    except Exception as exc:
        _meta_pipeline_status.update(
            {
                "running": False,
                "last_status": "error",
                "last_finished_at": kst_now().isoformat(timespec="seconds"),
                "last_error": str(exc),
            }
        )
        raise


@router.get("/meta-pipeline/status")
async def meta_pipeline_status(_=Depends(check_admin)):
    return _meta_pipeline_status


@router.get("/model-evaluation")
async def model_evaluation(target_date: Optional[str] = None, _=Depends(check_admin)):
    """Return the latest price-model evaluation report for the requested date."""
    report_date = target_date or kst_today().isoformat()
    path = _model_evaluation_path(report_date)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"model evaluation report not found for {report_date}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to read model evaluation report: {exc}")

    return {
        "date": report_date,
        "path": str(path.relative_to(_repo_root())),
        "report": payload,
    }


@router.post("/meta-pipeline/run")
async def manual_run_meta_pipeline(
    target_date: Optional[str] = None,
    skip_collect: bool = False,
    weather_lookback_days: int = 0,
    weather_max_requests_per_item: int = 16,
    weather_request_timeout_seconds: int = 8,
    background: bool = True,
    _=Depends(check_admin),
):
    """Run the metadata-driven pipeline and import outputs into the backend DB."""
    if _meta_pipeline_status.get("running"):
        raise HTTPException(status_code=409, detail="meta pipeline is already running")

    async def _run_bg():
        async with _pipeline_sem:
            try:
                await _run_meta_pipeline_process(
                    target_date,
                    skip_collect,
                    weather_lookback_days,
                    weather_max_requests_per_item,
                    weather_request_timeout_seconds,
                )
            except Exception as exc:
                print(f"[meta pipeline bg error] {exc}")

    if background:
        _asyncio.create_task(_run_bg())
        return {
            "status": "started",
            "target_date": target_date,
            "skip_collect": skip_collect,
            "weather_lookback_days": weather_lookback_days,
            "weather_max_requests_per_item": weather_max_requests_per_item,
            "weather_request_timeout_seconds": weather_request_timeout_seconds,
            "message": "meta pipeline started in background",
        }

    async with _pipeline_sem:
        try:
            return await _run_meta_pipeline_process(
                target_date,
                skip_collect,
                weather_lookback_days,
                weather_max_requests_per_item,
                weather_request_timeout_seconds,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


@router.post("/pipeline/run")
async def manual_run_pipeline(
    item_code: Optional[str] = None,
    background: bool = True,
    _=Depends(check_admin),
):
    """Compatibility route: route old pipeline calls to the mkmap_meta runner."""
    if item_code:
        raise HTTPException(
            status_code=400,
            detail="item_code-specific legacy pipeline runs are no longer supported; run the meta pipeline instead",
        )
    if _meta_pipeline_status.get("running"):
        raise HTTPException(status_code=409, detail="meta pipeline is already running")

    async def _run_bg():
        async with _pipeline_sem:
            try:
                await _run_meta_pipeline_process(None, False, 0)
            except Exception as exc:
                print(f"[pipeline bg error] {exc}")

    if background:
        _asyncio.create_task(_run_bg())
        return {
            "status": "started",
            "item_code": "all",
            "message": "meta pipeline started in background",
        }

    async with _pipeline_sem:
        try:
            return await _run_meta_pipeline_process(None, False, 0)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


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
    today = kst_today()

    latest_price_date = (await db.execute(select(func.max(DailyPrice.date)))).scalar()
    latest_weather_date = (await db.execute(select(func.max(DailyWeather.date)))).scalar()
    latest_signal_date = (await db.execute(select(func.max(RegionSignal.date)))).scalar()
    latest_forecast_date = (await db.execute(select(func.max(Forecast.base_date)))).scalar()

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
        "date": str(today),
        "db": {
            "items": item_count,
            "daily_prices": price_count,
            "daily_weather": weather_count,
            "region_signals": signal_count,
            "latest_forecast": str(latest_signal) if latest_signal else None,
            "seed_result": seed_result,
        },
        "data_freshness": {
            "daily_prices": _freshness_payload(latest_price_date, today, warn_after_days=2),
            "daily_weather": _weather_freshness_payload(latest_weather_date, today, warn_after_days=2),
            "region_signals": _freshness_payload(latest_signal_date, today, warn_after_days=1),
            "forecasts": _freshness_payload(latest_forecast_date, today, warn_after_days=1),
        },
        "scheduler": {
            "running": scheduler.running,
            "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in scheduler.get_jobs()],
        },
        "api_diagnostics": _latest_live_api_diagnostics(),
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

    settings = get_settings()
    target = kst_today() - timedelta(days=days_ago)

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
    from app.collectors.kamis import fetch_all_prices_for_date
    today = kst_today()
    result = await fetch_all_prices_for_date(today)
    return {
        "date": str(today),
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
