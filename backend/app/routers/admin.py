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
from typing import Any, Optional
from pydantic import BaseModel


class ImportOutputsRequest(BaseModel):
    signals: Optional[list[Any]] = None
    predictions: Optional[list[Any]] = None
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
    "last_duration_seconds": None,
    "last_date": None,
    "last_output_tail": [],
    "last_error": None,
    "last_step_completed": None,
    "last_step_failed": None,
    "last_step_summary": [],
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

    started_at = kst_now()
    _meta_pipeline_status.update(
        {
            "running": True,
            "last_status": "running",
            "last_started_at": started_at.isoformat(timespec="seconds"),
            "last_finished_at": None,
            "last_duration_seconds": None,
            "last_date": pipeline_date,
            "last_output_tail": [],
            "last_error": None,
            "last_step_completed": None,
            "last_step_failed": None,
            "last_step_summary": [],
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
        step_summary: list[dict] = []
        current_step: str | None = None
        import time as _time
        step_start = _time.monotonic()

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            output_lines.append(text)
            _meta_pipeline_status["last_output_tail"] = output_lines[-80:]

            # "== Step name ==" 패턴으로 step 추적
            if text.startswith("== ") and text.endswith(" =="):
                if current_step:
                    step_summary.append({"step": current_step, "status": "ok", "duration_s": round(_time.monotonic() - step_start, 1)})
                current_step = text[3:-3]
                step_start = _time.monotonic()
                _meta_pipeline_status["last_step_completed"] = current_step
            elif "[WARN]" in text and current_step:
                pass  # warn은 ok로 처리
            _meta_pipeline_status["last_step_summary"] = step_summary

        return_code = await process.wait()
        finished_at = kst_now()
        duration = round((finished_at - started_at).total_seconds(), 1)

        if current_step:
            step_summary.append({"step": current_step, "status": "ok" if return_code == 0 else "failed", "duration_s": round(_time.monotonic() - step_start, 1)})

        if return_code == 0:
            cache.clear_prefix("signals:")
            cache.clear_prefix("report:")
            _meta_pipeline_status.update(
                {
                    "running": False,
                    "last_status": "ok",
                    "last_finished_at": finished_at.isoformat(timespec="seconds"),
                    "last_duration_seconds": duration,
                    "last_error": None,
                    "last_output_tail": output_lines[-80:],
                    "last_step_failed": None,
                    "last_step_summary": step_summary,
                }
            )
        else:
            _meta_pipeline_status.update(
                {
                    "running": False,
                    "last_status": "error",
                    "last_finished_at": finished_at.isoformat(timespec="seconds"),
                    "last_duration_seconds": duration,
                    "last_error": f"process exited with code {return_code}",
                    "last_output_tail": output_lines[-80:],
                    "last_step_failed": current_step,
                    "last_step_summary": step_summary,
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


@router.post("/meta-pipeline/verify")
async def verify_meta_pipeline_outputs(
    target_date: Optional[str] = None,
    _=Depends(check_admin),
    db: AsyncSession = Depends(get_db),
):
    """Verify that today's pipeline outputs are present in the DB and pass basic sanity checks."""
    from sqlalchemy import func
    from app.models.signal import RegionSignal
    from app.models.forecast import Forecast
    from app.models.item import Item

    from datetime import date as _date
    _check_date_str = target_date or kst_today().isoformat()
    check_date = _date.fromisoformat(_check_date_str)
    checks: list[dict] = []

    def _check(name: str, ok: bool, detail: str = "") -> dict:
        result = {"check": name, "ok": ok}
        if detail:
            result["detail"] = detail
        checks.append(result)
        return result

    # Count signals for today
    signal_count = (
        await db.execute(
            select(func.count()).select_from(RegionSignal).where(RegionSignal.date == check_date)
        )
    ).scalar() or 0
    _check("signals_today", signal_count > 0, f"count={signal_count}")

    # Count forecasts for today
    forecast_count = (
        await db.execute(
            select(func.count()).select_from(Forecast).where(Forecast.base_date == check_date)
        )
    ).scalar() or 0
    _check("forecasts_today", forecast_count > 0, f"count={forecast_count}")

    # Check each item has a forecast
    items = (await db.execute(select(Item.item_code).where(Item.is_active == True))).scalars().all()
    for item_code in items:
        item_forecast = (
            await db.execute(
                select(func.count()).select_from(Forecast).where(
                    Forecast.item_code == item_code, Forecast.base_date == check_date
                )
            )
        ).scalar() or 0
        _check(f"forecast_{item_code}", item_forecast > 0, f"count={item_forecast}")

    # Check signal coverage per item
    for item_code in items:
        item_signals = (
            await db.execute(
                select(func.count()).select_from(RegionSignal).where(
                    RegionSignal.item_code == item_code, RegionSignal.date == check_date
                )
            )
        ).scalar() or 0
        _check(f"signals_{item_code}", item_signals > 0, f"count={item_signals}")

    passed = sum(1 for c in checks if c["ok"])
    failed = len(checks) - passed
    return {
        "ok": failed == 0,
        "date": _check_date_str,
        "passed": passed,
        "failed": failed,
        "total": len(checks),
        "checks": checks,
        "pipeline_status": {
            "last_date": _meta_pipeline_status.get("last_date"),
            "last_status": _meta_pipeline_status.get("last_status"),
            "last_step_completed": _meta_pipeline_status.get("last_step_completed"),
        },
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


@router.get("/debug/garlic-prices")
async def debug_garlic_prices(days: int = 35, db: AsyncSession = Depends(get_db), _=Depends(check_admin)):
    """garlic 최근 N일 가격 데이터 진단"""
    from datetime import timedelta
    from app.models.price import DailyPrice
    from app.timezone import kst_today
    start = kst_today() - timedelta(days=days)
    result = await db.execute(
        select(DailyPrice.date, DailyPrice.wholesale_price, DailyPrice.retail_price, DailyPrice.source)
        .where(DailyPrice.item_code == "garlic", DailyPrice.date >= start)
        .order_by(DailyPrice.date)
    )
    rows = result.all()
    return [{"date": str(r.date), "wholesale": r.wholesale_price, "retail": r.retail_price, "source": r.source} for r in rows]


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


@router.post("/debug/cleanup-mock-data")
async def cleanup_mock_data(db: AsyncSession = Depends(get_db), _=Depends(check_admin)):
    """daily_prices/daily_weather에서 source='mock_generator' 행 삭제.
    초기 시드 데이터가 실 데이터 계산을 오염시키는 문제 해결.
    실 데이터(kamis/kma 등)가 충분히 쌓인 후 1회만 실행하면 됨.
    """
    from sqlalchemy import delete as sa_delete, func
    from app.models.price import DailyPrice
    from app.models.weather import DailyWeather

    price_before = (await db.execute(
        select(func.count()).select_from(DailyPrice).where(DailyPrice.source == "mock_generator")
    )).scalar() or 0
    weather_before = (await db.execute(
        select(func.count()).select_from(DailyWeather).where(DailyWeather.source == "mock_generator")
    )).scalar() or 0

    await db.execute(sa_delete(DailyPrice).where(DailyPrice.source == "mock_generator"))
    await db.execute(sa_delete(DailyWeather).where(DailyWeather.source == "mock_generator"))
    await db.commit()

    return {
        "deleted_mock_prices": price_before,
        "deleted_mock_weather": weather_before,
    }


@router.post("/debug/fix-garlic-prices")
async def fix_garlic_prices(db: AsyncSession = Depends(get_db), _=Depends(check_admin)):
    """garlic daily_prices 중 1kg 단위 잘못 저장된 행(wholesale_price < 50000) 삭제 후 재sync.
    periodProductList kindcode=03(깐마늘) → 1kg 기준 가격을 10kg 기준으로 재수집.
    """
    from sqlalchemy import delete as sa_delete, func
    from app.models.price import DailyPrice
    from app.collectors.sync import sync_prices

    # COUNT before delete (asyncpg rowcount unreliable)
    deleted = (await db.execute(
        select(func.count()).select_from(DailyPrice).where(
            DailyPrice.item_code == "garlic",
            DailyPrice.source == "kamis",
            DailyPrice.wholesale_price < 50000,
        )
    )).scalar() or 0

    # 잘못된 단위 행 삭제 (garlic 10kg 기준 최소가 50,000원 이상이어야 함)
    await db.execute(
        sa_delete(DailyPrice).where(
            DailyPrice.item_code == "garlic",
            DailyPrice.source == "kamis",
            DailyPrice.wholesale_price < 50000,
        )
    )
    await db.commit()

    # 최근 35일 재sync (10배 multiplier 적용됨)
    sync_result = await sync_prices(days_back=35)

    return {"deleted_wrong_unit_rows": deleted, "sync": sync_result}


@router.post("/import-outputs")
async def import_outputs(
    target_date: str,
    body: ImportOutputsRequest,
    _=Depends(check_admin),
    db: AsyncSession = Depends(get_db),
):
    """로컬에서 생성한 signal/forecast JSON을 DB에 직접 import.
    Railway API 키 없이 로컬 파이프라인 결과를 운영 DB에 반영할 때 사용.
    Body: {"signals": [...], "predictions": [...]}
    """
    from sqlalchemy import delete
    from app.models.signal import RegionSignal
    from app.models.forecast import Forecast
    import datetime

    try:
        date_obj = datetime.date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {target_date}")

    result: dict = {"date": target_date, "signals_imported": 0, "forecasts_imported": 0}

    signals = body.signals
    predictions = body.predictions

    if signals is not None:
        rows: list[RegionSignal] = []
        item_codes: set[str] = set()
        for item_payload in signals:
            if not isinstance(item_payload, dict):
                continue
            item_code = str(item_payload.get("item_code") or "")
            if not item_code:
                continue
            item_codes.add(item_code)
            data_status = item_payload.get("data_status") if isinstance(item_payload.get("data_status"), dict) else {}
            for signal in item_payload.get("signals") or []:
                if not isinstance(signal, dict):
                    continue
                top_factors = signal.get("top_factors") if isinstance(signal.get("top_factors"), list) else []
                rows.append(RegionSignal(
                    item_code=item_code,
                    region_code=str(signal.get("region_code") or ""),
                    region_name=str(signal.get("region_name") or ""),
                    date=date_obj,
                    risk_score=round(float(signal.get("risk_score") or 0.0) * 100, 2),
                    risk_level={"normal":"normal","watch":"caution","warning":"warning","critical":"high","high":"high"}.get(str(signal.get("risk_level") or ""), "normal"),
                    supply_shock=round(float(next((f.get("contribution",0) for f in top_factors if isinstance(f,dict) and f.get("factor")=="production_region_weight"), 0)), 4),
                    price_effect=("up" if "up" in str(signal.get("price_effect","")) else "down" if "down" in str(signal.get("price_effect","")) else "neutral"),
                    weather_summary={"feature_count": data_status.get("weather",0), "weather_pressure": next((f.get("contribution",0) for f in top_factors if isinstance(f,dict) and f.get("factor")=="weather_pressure"), 0)},
                    market_summary={"price_feature_count": data_status.get("prices",0), "event_feature_count": data_status.get("events",0), "top_factors": top_factors},
                    summary_text=signal.get("summary"),
                ))
        for item_code in item_codes:
            await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code, RegionSignal.date == date_obj))
        db.add_all(rows)
        await db.commit()
        result["signals_imported"] = len(rows)

    if predictions is not None:
        rows_f: list[Forecast] = []
        item_codes_f: set[str] = set()
        for pred in predictions:
            if not isinstance(pred, dict):
                continue
            item_code = str(pred.get("item_code") or "")
            if not item_code:
                continue
            item_codes_f.add(item_code)
            adjusted_change = float(pred.get("risk_adjusted_next_change", pred.get("predicted_next_change", 0.0)) or 0.0)
            pure_change = float(pred.get("predicted_next_change") or 0.0)
            risk_overlay = pred.get("risk_overlay") if isinstance(pred.get("risk_overlay"), dict) else {}
            up_prob = round(max(0.0, min(1.0, float(pred.get("up_probability_14d") or (0.5 + max(-0.2, min(0.2, adjusted_change * 5.0)))))), 4)
            rows_f.append(Forecast(
                item_code=item_code,
                base_date=date_obj,
                model_version="mkmap_meta_hybrid_linear_risk_overlay_v2_" + str(pred.get("model_scope","global")),
                direction_14d=("up" if str(pred.get("risk_adjusted_direction","stable")) == "up" else "down" if str(pred.get("risk_adjusted_direction","")) == "down" else "neutral"),
                up_probability_14d=up_prob,
                surge_probability_14d=round(max(0.0, min(1.0, float(pred.get("surge_probability_14d") or 0.0))), 4),
                volatility_risk_30d=("high" if float(risk_overlay.get("max_risk_score") or 0) >= 0.45 else "medium" if float(risk_overlay.get("max_risk_score") or 0) >= 0.25 else "low"),
                bottom_probability=round(max(0.0, min(1.0, float(pred.get("bottom_probability") or (1.0 - up_prob)))), 4),
                top_factors=[
                    {"factor":"price_lag_model","contribution":abs(round(pure_change,6)),"direction":"up" if pure_change>=0 else "down"},
                    {"factor":"risk_overlay","contribution":abs(round(adjusted_change-pure_change,6)),"direction":"up" if adjusted_change>=pure_change else "down"},
                ] + ([{"factor": risk_overlay.get("top_factor") or "region_risk", "contribution": round(float(risk_overlay.get("max_risk_score") or 0), 6), "direction": "up"}] if risk_overlay else []),
                national_supply_shock=round(adjusted_change - pure_change, 6),
                confidence=str(pred.get("confidence") or ("medium" if risk_overlay else "low")),
            ))
        for item_code in item_codes_f:
            await db.execute(delete(Forecast).where(Forecast.item_code == item_code, Forecast.base_date == date_obj))
        db.add_all(rows_f)
        await db.commit()
        result["forecasts_imported"] = len(rows_f)

    return result


# ── Bulk historical price import (Railway DB expansion) ───────────────────────

class PriceRow(BaseModel):
    item_code: str
    date: str
    wholesale_price: float
    retail_price: Optional[float] = None
    market: str = ""
    grade: str = ""
    source: str = "kamis"


class ImportPricesRequest(BaseModel):
    prices: list[PriceRow]


@router.post("/import-prices")
async def import_prices(
    body: ImportPricesRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(check_admin),
):
    """로컬에서 수집한 KAMIS 대량 가격 데이터를 Railway DB에 UPSERT.

    용도: KAMIS API는 수년치 과거 데이터 제공 가능하나 Railway 자동 sync는
    최근 90일만 수집했음. 이 엔드포인트로 다년치 데이터를 한 번에 벌크 import.

    Body: {"prices": [{"item_code","date","wholesale_price","retail_price","market","grade","source"}]}
    UPSERT 기준: (item_code, date, source)
    """
    import datetime
    from app.models.price import DailyPrice

    if not body.prices:
        return {"saved": 0, "message": "no data"}

    valid_rows = []
    skipped = 0
    for row in body.prices:
        try:
            date_obj = datetime.date.fromisoformat(row.date)
            if row.wholesale_price <= 0:
                skipped += 1
                continue
            valid_rows.append({
                "item_code": row.item_code,
                "date": date_obj,
                "wholesale_price": row.wholesale_price,
                "retail_price": row.retail_price,
                "market": row.market,
                "grade": row.grade,
                "source": row.source,
            })
        except (ValueError, TypeError):
            skipped += 1

    if not valid_rows:
        return {"saved": 0, "skipped": skipped, "message": "no valid rows"}

    # Batch UPSERT in chunks of 500 to avoid parameter limit
    saved = 0
    chunk_size = 500
    for i in range(0, len(valid_rows), chunk_size):
        chunk = valid_rows[i:i + chunk_size]
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(DailyPrice).values(chunk).on_conflict_do_update(
                index_elements=["item_code", "date", "source"],
                set_={
                    "wholesale_price": pg_insert(DailyPrice).excluded.wholesale_price,
                    "retail_price": pg_insert(DailyPrice).excluded.retail_price,
                    "market": pg_insert(DailyPrice).excluded.market,
                    "grade": pg_insert(DailyPrice).excluded.grade,
                }
            )
            result = await db.execute(stmt)
            await db.commit()
            saved += result.rowcount or len(chunk)
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Chunk {i//chunk_size} UPSERT failed: {e}")

    items = list({r["item_code"] for r in valid_rows})
    date_range = (
        min(str(r["date"]) for r in valid_rows),
        max(str(r["date"]) for r in valid_rows),
    )
    return {
        "saved": saved,
        "skipped": skipped,
        "total_input": len(body.prices),
        "items": items,
        "date_range": {"start": date_range[0], "end": date_range[1]},
    }


@router.post("/sync/historical")
async def sync_historical_prices(
    days_back: int = 1825,
    chunk_days: int = 90,
    background: bool = True,
    _=Depends(check_admin),
):
    """Railway 서버에서 직접 KAMIS API를 청크 단위로 호출해 수년치 가격 수집.

    days_back=1825 → 5년. chunk_days=90씩 나눠 순차 요청.
    KAMIS periodProductList는 단일 요청으로 대용량 조회 시 연도 파싱 오류가 있어
    90일 청크로 분할 처리.
    """
    import asyncio
    import datetime as _dt
    from app.collectors.kamis import fetch_period_prices, ITEM_CODE_MAP
    from app.models.price import DailyPrice
    from app.database import AsyncSessionLocal

    async def _run_chunked():
        end = _dt.date.today()
        start = end - _dt.timedelta(days=days_back)
        total_saved = 0
        total_chunks = 0

        # 시간 역순으로 청크 처리 (최신 → 과거)
        chunk_end = end
        while chunk_end > start:
            chunk_start = max(start, chunk_end - _dt.timedelta(days=chunk_days - 1))
            print(f"[sync/historical] chunk {chunk_start} ~ {chunk_end}")
            saved_chunk = 0

            for item_code in ITEM_CODE_MAP:
                try:
                    rows = await fetch_period_prices(item_code, chunk_start, chunk_end)
                    if not rows:
                        continue
                    values = [
                        {
                            "item_code": r["item_code"],
                            "date": r["date"],
                            "market": r.get("market", ""),
                            "grade": r.get("grade", ""),
                            "wholesale_price": r["wholesale_price"],
                            "retail_price": r.get("retail_price"),
                            "source": "kamis",
                        }
                        for r in rows if r.get("wholesale_price", 0) > 0
                    ]
                    if not values:
                        continue
                    async with AsyncSessionLocal() as db:
                        try:
                            from sqlalchemy.dialects.postgresql import insert as pg_insert
                            stmt = pg_insert(DailyPrice).values(values).on_conflict_do_update(
                                index_elements=["item_code", "date", "source"],
                                set_={
                                    "wholesale_price": pg_insert(DailyPrice).excluded.wholesale_price,
                                    "retail_price": pg_insert(DailyPrice).excluded.retail_price,
                                }
                            )
                            result = await db.execute(stmt)
                            await db.commit()
                            saved_chunk += result.rowcount or len(values)
                        except Exception as e:
                            await db.rollback()
                            print(f"[sync/historical] DB error {item_code}: {e}")
                except Exception as e:
                    print(f"[sync/historical] fetch error {item_code}: {e}")
                await asyncio.sleep(0.5)

            total_saved += saved_chunk
            total_chunks += 1
            print(f"[sync/historical] chunk done saved={saved_chunk} total={total_saved}")
            chunk_end = chunk_start - _dt.timedelta(days=1)
            await asyncio.sleep(2)  # KAMIS API 과부하 방지

        print(f"[sync/historical] ALL DONE: chunks={total_chunks} total_saved={total_saved}")

    if background:
        asyncio.create_task(_run_chunked())
        total_chunks_est = (days_back + chunk_days - 1) // chunk_days
        return {
            "status": "started",
            "days_back": days_back,
            "chunk_days": chunk_days,
            "estimated_chunks": total_chunks_est,
            "message": f"{days_back}일 / {chunk_days}일 청크 = {total_chunks_est}회 수집 중 — /admin/debug/price-counts 로 확인"
        }
    else:
        await _run_chunked()
        return {"status": "ok", "days_back": days_back}



# ── LightGBM server-side training ────────────────────────────────────────────

_lgbm_train_status: dict = {
    "running": False,
    "last_status": None,
    "last_started_at": None,
    "last_finished_at": None,
    "last_duration_seconds": None,
    "last_results": None,
    "last_error": None,
}
_lgbm_sem = _asyncio.Semaphore(1)


def _build_price_features_from_db(
    price_rows: list,
    item_weather: "dict | None" = None,
    horizon: int = 14,
) -> "pd.DataFrame":
    """DailyPrice rows → per-item feature DataFrame (lag + rolling + weather features)."""
    import pandas as pd
    import numpy as np
    from datetime import timedelta

    records = [
        {"item_code": r.item_code, "date": r.date, "price": float(r.wholesale_price)}
        for r in price_rows
        if r.wholesale_price and r.wholesale_price > 0
    ]
    if not records:
        return pd.DataFrame()

    df_raw = pd.DataFrame(records).sort_values(["item_code", "date"])
    LAGS = [1, 2, 3, 7, 14, 21, 28]
    WINDOWS = [7, 14, 30, 60]

    pieces = []
    for item_code, grp in df_raw.groupby("item_code"):
        g = grp.set_index("date").sort_index()
        feat = pd.DataFrame(index=g.index)
        feat["item_code"] = item_code
        feat["price"] = g["price"]

        for lag in LAGS:
            feat[f"lag_{lag}"] = g["price"].shift(lag)
        for w in WINDOWS:
            feat[f"ma_{w}"] = g["price"].shift(1).rolling(w, min_periods=max(1, w // 2)).mean()
            feat[f"std_{w}"] = g["price"].shift(1).rolling(w, min_periods=max(1, w // 2)).std()

        feat["ret_1"] = (g["price"] - g["price"].shift(1)) / (g["price"].shift(1).abs() + 1e-8)
        feat["ret_7"] = (g["price"] - g["price"].shift(7)) / (g["price"].shift(7).abs() + 1e-8)
        feat["ret_14"] = (g["price"] - g["price"].shift(14)) / (g["price"].shift(14).abs() + 1e-8)

        feat["target"] = (g["price"] - g["price"].shift(horizon)) / (g["price"].shift(horizon).abs() + 1e-8)
        feat["direction"] = (feat["target"] > 0).astype(int)

        feat["month"] = [d.month for d in g.index]
        feat["dayofyear"] = [d.timetuple().tm_yday for d in g.index]
        feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
        feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)
        feat["doy_sin"] = np.sin(2 * np.pi * feat["dayofyear"] / 365)
        feat["doy_cos"] = np.cos(2 * np.pi * feat["dayofyear"] / 365)

        # Weather rolling features from daily_weather DB
        if item_weather and item_code in item_weather:
            wmap = item_weather[item_code]
            temps_7, rains_7, hums_7 = [], [], []
            temps_30, rains_30 = [], []
            for d in g.index:
                t7 = [wmap[d - timedelta(days=i)]["temp"]
                      for i in range(1, 8) if (d - timedelta(days=i)) in wmap
                      and wmap[d - timedelta(days=i)]["temp"] is not None]
                r7 = [wmap[d - timedelta(days=i)]["rain"]
                      for i in range(1, 8) if (d - timedelta(days=i)) in wmap
                      and wmap[d - timedelta(days=i)]["rain"] is not None]
                h7 = [wmap[d - timedelta(days=i)]["humidity"]
                      for i in range(1, 8) if (d - timedelta(days=i)) in wmap
                      and wmap[d - timedelta(days=i)]["humidity"] is not None]
                t30 = [wmap[d - timedelta(days=i)]["temp"]
                       for i in range(1, 31) if (d - timedelta(days=i)) in wmap
                       and wmap[d - timedelta(days=i)]["temp"] is not None]
                r30 = [wmap[d - timedelta(days=i)]["rain"]
                       for i in range(1, 31) if (d - timedelta(days=i)) in wmap
                       and wmap[d - timedelta(days=i)]["rain"] is not None]
                temps_7.append(sum(t7) / len(t7) if t7 else 0.0)
                rains_7.append(sum(r7) if r7 else 0.0)
                hums_7.append(sum(h7) / len(h7) if h7 else 0.0)
                temps_30.append(sum(t30) / len(t30) if t30 else 0.0)
                rains_30.append(sum(r30) if r30 else 0.0)
            feat["temp_7d_avg"] = temps_7
            feat["rain_7d_sum"] = rains_7
            feat["humidity_7d_avg"] = hums_7
            feat["temp_30d_avg"] = temps_30
            feat["rain_30d_sum"] = rains_30
        else:
            feat["temp_7d_avg"] = 0.0
            feat["rain_7d_sum"] = 0.0
            feat["humidity_7d_avg"] = 0.0
            feat["temp_30d_avg"] = 0.0
            feat["rain_30d_sum"] = 0.0

        feat["base_date"] = feat.index
        pieces.append(feat.reset_index(drop=True))

    if not pieces:
        return pd.DataFrame()

    df = pd.concat(pieces, ignore_index=True)
    df = df.dropna(subset=["target", "lag_14", "ma_7"])
    # Fill remaining NaN with 0 (weather features on dates with no data, sparse lags)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].fillna(0.0)
    return df


def _train_lgbm_for_item(df_item: "pd.DataFrame", item_code: str, horizon: int = 14) -> dict:
    """Train Ridge + LightGBM ensemble on a single item. Returns metrics dict."""
    import numpy as np
    import pickle
    import base64

    FEATURE_COLS = [c for c in df_item.columns if c not in
                    ("item_code", "price", "target", "direction", "base_date", "month", "dayofyear")]

    # Time-ordered 3-way split: 65 / 15 / 20
    n = len(df_item)
    i_val = int(n * 0.65)
    i_test = int(n * 0.80)
    train = df_item.iloc[:i_val]
    val = df_item.iloc[i_val:i_test]
    test = df_item.iloc[i_test:]

    if len(train) < 30 or len(val) < 5 or len(test) < 5:
        return {"item_code": item_code, "error": f"insufficient data: n={n}"}

    X_tr = train[FEATURE_COLS].values.astype(float)
    y_tr = train["target"].values
    X_val = val[FEATURE_COLS].values.astype(float)
    y_val = val["target"].values
    X_test = test[FEATURE_COLS].values.astype(float)
    y_test = test["target"].values
    dir_test = test["direction"].values

    # sklearn Ridge
    try:
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_val_s = scaler.transform(X_val)
        X_test_s = scaler.transform(X_test)
        ridge = Ridge(alpha=0.01)
        ridge.fit(X_tr_s, y_tr)
        pred_val_ridge = ridge.predict(X_val_s)
        pred_test_ridge = ridge.predict(X_test_s)
    except Exception as e:
        return {"item_code": item_code, "error": f"Ridge failed: {e}"}

    # LightGBM
    pred_val_lgbm = None
    pred_test_lgbm = None
    lgbm_model = None
    try:
        import lightgbm as lgb
        dtrain = lgb.Dataset(X_tr, label=y_tr)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
        params = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_data_in_leaf": 5,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "lambda_l1": 0.1,
            "lambda_l2": 0.1,
            "verbose": -1,
            "num_threads": 1,
        }
        callbacks = [lgb.early_stopping(20, verbose=False), lgb.log_evaluation(-1)]
        lgbm_model = lgb.train(
            params, dtrain, num_boost_round=300,
            valid_sets=[dval], callbacks=callbacks
        )
        pred_val_lgbm = lgbm_model.predict(X_val)
        pred_test_lgbm = lgbm_model.predict(X_test)
    except Exception as e:
        print(f"[lgbm] {item_code} LightGBM failed: {e}, using Ridge only")

    # Ensemble (simple average if both available)
    if pred_val_lgbm is not None:
        pred_val_ens = (pred_val_ridge + pred_val_lgbm) / 2
        pred_test_ens = (pred_test_ridge + pred_test_lgbm) / 2
    else:
        pred_val_ens = pred_val_ridge
        pred_test_ens = pred_test_ridge

    # Threshold tuning on val only
    best_thr, best_dir = 0.0, 0.0
    for thr in [t / 200 for t in range(-20, 21)]:
        dir_acc = float(np.mean((pred_val_ens > thr).astype(int) == val["direction"].values))
        if dir_acc > best_dir:
            best_dir, best_thr = dir_acc, thr

    # Probability calibration: Isotonic Regression on val predictions
    # Maps raw ensemble scores → calibrated probabilities
    calibrator = None
    calibrator_b64 = None
    try:
        from sklearn.isotonic import IsotonicRegression
        # Convert raw scores to pseudo-probabilities via sigmoid, then calibrate
        def _sigmoid(x):
            return 1.0 / (1.0 + np.exp(-np.clip(x * 20, -20, 20)))

        val_probs = _sigmoid(pred_val_ens - best_thr)
        val_labels = val["direction"].values.astype(float)
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(val_probs, val_labels)
        # Calibrated test predictions
        test_probs_raw = _sigmoid(pred_test_ens - best_thr)
        test_probs_cal = calibrator.predict(test_probs_raw)
        calibrated_dir_test_acc = float(np.mean((test_probs_cal > 0.5).astype(int) == dir_test))
        calibrator_b64 = base64.b64encode(pickle.dumps(calibrator)).decode()
    except Exception as e:
        print(f"[lgbm] {item_code} calibration failed: {e}")
        calibrated_dir_test_acc = None
        test_probs_cal = None

    # Test metrics
    mae_test = float(np.mean(np.abs(pred_test_ens - y_test)))
    dir_test_acc = float(np.mean((pred_test_ens > best_thr).astype(int) == dir_test))
    mae_val = float(np.mean(np.abs(pred_val_ens - y_val)))
    overfit = mae_test / mae_val if mae_val > 0 else None

    return {
        "item_code": item_code,
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "features": len(FEATURE_COLS),
        "threshold": best_thr,
        "val_mae": round(mae_val, 5),
        "test_mae": round(mae_test, 5),
        "test_dir_acc": round(dir_test_acc, 4),
        "calibrated_dir_acc": round(calibrated_dir_test_acc, 4) if calibrated_dir_test_acc else None,
        "overfit_ratio": round(overfit, 3) if overfit else None,
        "lgbm_best_iter": lgbm_model.best_iteration if lgbm_model else None,
        "_objects": {
            "scaler": scaler,
            "ridge": ridge,
            "lgbm": lgbm_model,
            "calibrator": calibrator,
            "threshold": best_thr,
        },
    }


async def _run_lgbm_training(db: "AsyncSession") -> dict:
    """Fetch price + weather data from Railway DB, train ensemble per item, save results."""
    import time
    from app.models.price import DailyPrice
    from app.models.weather import DailyWeather

    started = time.monotonic()
    results_per_item = {}

    # Load price data
    result = await db.execute(
        select(DailyPrice.item_code, DailyPrice.date, DailyPrice.wholesale_price)
        .where(DailyPrice.wholesale_price > 0)
        .order_by(DailyPrice.item_code, DailyPrice.date)
    )
    price_rows = result.all()
    if not price_rows:
        return {"error": "no price data in DB"}

    # Load weather data: region_code → date → {avg_temp, precipitation, humidity}
    # CROP_REGION_MAP의 region_code 목록
    ITEM_WEATHER_REGIONS = {
        "cabbage":     ["KR-42", "KR-43"],
        "radish":      ["KR-42", "KR-48"],
        "onion":       ["KR-46", "KR-48"],
        "green_onion": ["KR-46", "KR-41"],
        "garlic":      ["KR-47", "KR-46"],
    }
    all_region_codes = list({r for rs in ITEM_WEATHER_REGIONS.values() for r in rs})
    weather_result = await db.execute(
        select(DailyWeather.region_code, DailyWeather.date,
               DailyWeather.avg_temp, DailyWeather.precipitation, DailyWeather.humidity)
        .where(DailyWeather.region_code.in_(all_region_codes))
        .order_by(DailyWeather.region_code, DailyWeather.date)
    )
    weather_rows = weather_result.all()

    # Build weather lookup: {region_code: {date: {temp, rain, humidity}}}
    weather_by_region: dict = {}
    for r in weather_rows:
        weather_by_region.setdefault(r.region_code, {})[r.date] = {
            "temp": r.avg_temp,
            "rain": r.precipitation,
            "humidity": r.humidity,
        }

    # Build item-level weather: average across item's regions
    # {item_code: {date: {temp, rain, humidity}}}
    item_weather: dict = {}
    for item_code, region_codes in ITEM_WEATHER_REGIONS.items():
        daily: dict = {}
        for rc in region_codes:
            for d, w in weather_by_region.get(rc, {}).items():
                if d not in daily:
                    daily[d] = {"temps": [], "rains": [], "humids": []}
                if w["temp"] is not None: daily[d]["temps"].append(w["temp"])
                if w["rain"] is not None: daily[d]["rains"].append(w["rain"])
                if w["humidity"] is not None: daily[d]["humids"].append(w["humidity"])
        item_weather[item_code] = {
            d: {
                "temp": sum(v["temps"]) / len(v["temps"]) if v["temps"] else None,
                "rain": sum(v["rains"]) / len(v["rains"]) if v["rains"] else None,
                "humidity": sum(v["humids"]) / len(v["humids"]) if v["humids"] else None,
            }
            for d, v in daily.items()
        }

    # Build features (runs in thread to avoid blocking event loop)
    import asyncio
    import functools

    try:
        import pandas as pd
    except ImportError:
        return {"error": "pandas not available on Railway"}

    import json as _json
    import pickle as _pickle
    import numpy as _np
    from app.models.forecast import Forecast
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    model_dir = REPO_ROOT / "data" / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    HORIZONS = [14, 30, 60, 90]

    # price_rows를 한 번만 기본 feature로 변환 (horizon-independent 부분)
    # 각 horizon별로 target만 다름 → horizon별로 별도 df 빌드
    for horizon in HORIZONS:
        df = await asyncio.get_running_loop().run_in_executor(
            None, functools.partial(_build_price_features_from_db, price_rows, item_weather, horizon)
        )
        if df.empty:
            results_per_item[f"horizon_{horizon}"] = {"error": "feature table empty"}
            continue

        item_codes = df["item_code"].unique().tolist()
        for item_code in item_codes:
            key = f"{item_code}_h{horizon}"
            df_item = df[df["item_code"] == item_code].copy()
            item_result = await asyncio.get_running_loop().run_in_executor(
                None, functools.partial(_train_lgbm_for_item, df_item, item_code, horizon)
            )
            _objects = item_result.pop("_objects", {})
            results_per_item[key] = {k: v for k, v in item_result.items()}

            if "error" in item_result:
                continue

            # Save model .pkl
            pkl_path = model_dir / f"lgbm_ensemble_{item_code}_h{horizon}.pkl"
            pkl_path.write_bytes(_pickle.dumps(_objects))
            # Save metrics JSON
            metrics_path = model_dir / f"lgbm_ensemble_{item_code}_h{horizon}.json"
            metrics_path.write_text(
                _json.dumps(item_result, default=str, ensure_ascii=False), encoding="utf-8"
            )

            # Predict today → save Forecast row
            try:
                scaler = _objects.get("scaler")
                ridge = _objects.get("ridge")
                lgbm_model = _objects.get("lgbm")
                calibrator = _objects.get("calibrator")
                threshold = float(_objects.get("threshold", 0.0))

                df_item_sorted = df_item.sort_values("base_date")
                FEATURE_COLS = [c for c in df_item.columns if c not in
                                ("item_code", "price", "target", "direction", "base_date", "month", "dayofyear")]
                latest = df_item_sorted.iloc[-1]
                X_latest = latest[FEATURE_COLS].values.astype(float).reshape(1, -1)

                X_scaled = scaler.transform(X_latest)
                pred_ridge = float(ridge.predict(X_scaled)[0])
                pred_lgbm = float(lgbm_model.predict(X_latest)[0]) if lgbm_model else None
                pred_ens = (pred_ridge + pred_lgbm) / 2 if pred_lgbm is not None else pred_ridge

                direction = "up" if pred_ens > threshold else "down"
                if calibrator is not None:
                    sigmoid_val = 1.0 / (1.0 + _np.exp(-_np.clip((pred_ens - threshold) * 20, -20, 20)))
                    up_prob = float(calibrator.predict([sigmoid_val])[0])
                else:
                    up_prob = float(1.0 / (1.0 + _np.exp(-_np.clip((pred_ens - threshold) * 10, -10, 10))))
                up_prob = max(0.05, min(0.95, up_prob))

                today = kst_today()
                top_factors = [
                    {"factor": "lgbm_ensemble", "contribution": round(abs(pred_ens), 6), "direction": direction},
                ]
                stmt = pg_insert(Forecast).values([{
                    "item_code": item_code,
                    "base_date": today,
                    "horizon_days": horizon,
                    "model_version": f"lgbm_v2_{item_code}_h{horizon}",
                    "direction": direction,
                    "up_probability": round(up_prob, 4),
                    "direction_14d": direction if horizon == 14 else None,
                    "up_probability_14d": round(up_prob, 4) if horizon == 14 else None,
                    "surge_probability_14d": round(max(0.0, up_prob - 0.6), 4) if horizon == 14 else None,
                    "volatility_risk_30d": "high" if item_result.get("overfit_ratio", 0) and item_result["overfit_ratio"] > 2 else "medium",
                    "bottom_probability": round(1.0 - up_prob, 4),
                    "top_factors": top_factors,
                    "national_supply_shock": round(pred_ens, 6),
                    "confidence": "high" if item_result.get("test_dir_acc", 0) >= 0.65 else "medium",
                }]).on_conflict_do_update(
                    index_elements=["item_code", "base_date", "horizon_days"],
                    set_={
                        "model_version": pg_insert(Forecast).excluded.model_version,
                        "direction": pg_insert(Forecast).excluded.direction,
                        "up_probability": pg_insert(Forecast).excluded.up_probability,
                        "direction_14d": pg_insert(Forecast).excluded.direction_14d,
                        "up_probability_14d": pg_insert(Forecast).excluded.up_probability_14d,
                        "surge_probability_14d": pg_insert(Forecast).excluded.surge_probability_14d,
                        "volatility_risk_30d": pg_insert(Forecast).excluded.volatility_risk_30d,
                        "bottom_probability": pg_insert(Forecast).excluded.bottom_probability,
                        "top_factors": pg_insert(Forecast).excluded.top_factors,
                        "national_supply_shock": pg_insert(Forecast).excluded.national_supply_shock,
                        "confidence": pg_insert(Forecast).excluded.confidence,
                    }
                )
                await db.execute(stmt)
                await db.commit()
                results_per_item[key]["forecast_saved"] = True
                results_per_item[key]["forecast_direction"] = direction
                results_per_item[key]["forecast_up_prob"] = round(up_prob, 4)
            except Exception as e:
                results_per_item[key]["forecast_error"] = str(e)[:200]
                await db.rollback()

    elapsed = round(time.monotonic() - started, 1)
    return {
        "elapsed_seconds": elapsed,
        "items": results_per_item,
        "total_rows": len(price_rows),
        "horizons": HORIZONS,
    }


@router.post("/train/lightgbm")
async def train_lightgbm(
    background: bool = True,
    _=Depends(check_admin),
    db: AsyncSession = Depends(get_db),
):
    """Railway DB 가격 데이터로 품목별 Ridge+LightGBM 앙상블 학습.

    Railway Docker에 설치된 sklearn==1.5.2 + lightgbm==4.5.0 사용.
    모델은 /data/model/lgbm_ensemble_{item}.json 에 저장.
    background=True(기본): 즉시 202 반환, 백그라운드 학습.
    GET /admin/train/lightgbm/status 로 진행 확인.
    """
    if _lgbm_train_status["running"]:
        raise HTTPException(status_code=409, detail="LightGBM training already running")

    from app.timezone import kst_now

    async def _bg():
        async with _lgbm_sem:
            started_at = kst_now()
            _lgbm_train_status.update({
                "running": True,
                "last_status": "running",
                "last_started_at": started_at.isoformat(timespec="seconds"),
                "last_finished_at": None,
                "last_results": None,
                "last_error": None,
            })
            try:
                async with __import__("app.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as sess:
                    result = await _run_lgbm_training(sess)
                finished_at = kst_now()
                _lgbm_train_status.update({
                    "running": False,
                    "last_status": "ok" if "error" not in result else "error",
                    "last_finished_at": finished_at.isoformat(timespec="seconds"),
                    "last_duration_seconds": result.get("elapsed_seconds"),
                    "last_results": {k: v for k, v in result.items() if k != "model"},
                    "last_error": result.get("error"),
                })
            except Exception as exc:
                _lgbm_train_status.update({
                    "running": False,
                    "last_status": "error",
                    "last_finished_at": kst_now().isoformat(timespec="seconds"),
                    "last_error": str(exc),
                })
                print(f"[lgbm train error] {exc}")

    if background:
        _asyncio.create_task(_bg())
        return {"status": "started", "message": "LightGBM training started in background. GET /admin/train/lightgbm/status to check."}

    # Foreground
    async with _lgbm_sem:
        try:
            return await _run_lgbm_training(db)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))


@router.get("/train/lightgbm/status")
async def lgbm_training_status(_=Depends(check_admin)):
    """LightGBM 학습 진행 상태 및 최근 결과 조회."""
    return _lgbm_train_status


@router.post("/train/lightgbm/reset")
async def lgbm_training_reset(_=Depends(check_admin)):
    """Stuck된 LightGBM 학습 상태를 강제 리셋 (running=False)."""
    _lgbm_train_status.update({"running": False, "last_status": "reset", "last_error": "manual reset"})
    return {"status": "reset", "message": "running flag cleared. You may now trigger a new training."}


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
