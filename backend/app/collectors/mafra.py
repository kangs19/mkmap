"""MAFRA 오픈API 수집 — 농업용수 저수율/강수(가뭄 지표).

데이터셋: Grid_20250220000000000669_1 (지역별 누적 강수량 및 농업용수 저수율)
서버: http://211.237.50.150:7080/openapi/{key}/json/{grid}/{start}/{end}
- 필터 미지원, 페이지 상한 1000건 → 전체 페이징 후 최신월 집계
- AREA_SPR_CD(저수지코드)는 시군구 매핑 테이블이 없어 우선 전국 지표로 저장

Railway 환경변수 MAFRA_API_KEY (또는 AGROMARKET_API_KEY) 필요.
"""
import asyncio
import json
import logging
import urllib.request
from collections import defaultdict
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.drought import DroughtIndex
from app.timezone import kst_today

logger = logging.getLogger(__name__)

MAFRA_BASE = "http://211.237.50.150:7080/openapi"
DS_RESERVOIR = "Grid_20250220000000000669_1"
_PAGE = 1000
_MAX_PAGES = 70


def _mafra_key() -> str:
    s = get_settings()
    return s.mafra_api_key or s.agromarket_api_key


def _fetch_page_sync(key: str, grid: str, start: int, end: int) -> list:
    url = f"{MAFRA_BASE}/{key}/json/{grid}/{start}/{end}"
    with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    grid_key = next(iter(data.keys()))
    return data.get(grid_key, {}).get("row", []) or []


def _collect_reservoir_sync(key: str) -> dict:
    """전체 페이징 → 최신 연월의 전국 평균 저수율/강수량."""
    by_ym_rate = defaultdict(list)
    by_ym_rain = defaultdict(list)
    for page in range(_MAX_PAGES):
        start = page * _PAGE + 1
        end = start + _PAGE - 1
        try:
            rows = _fetch_page_sync(key, DS_RESERVOIR, start, end)
        except Exception as exc:
            logger.warning("[mafra] reservoir page %s fail: %s", page, exc)
            break
        if not rows:
            break
        for x in rows:
            ym = x.get("TOT_YM")
            rate = x.get("STWTR_RTO_MSRVL")
            rain = x.get("RNFL_MSRVL")
            if ym and rate is not None:
                by_ym_rate[ym].append(rate)
            if ym and rain is not None:
                by_ym_rain[ym].append(rain)
        if len(rows) < _PAGE:
            break
    if not by_ym_rate:
        return {}
    latest = max(by_ym_rate.keys())
    rates = by_ym_rate[latest]
    rains = by_ym_rain.get(latest, [])
    return {
        "base_ym": latest,
        "reservoir_rate": round(sum(rates) / len(rates), 1),
        "rainfall_avg": round(sum(rains) / len(rains), 1) if rains else None,
        "region_count": len(rates),
    }


async def collect_drought_index() -> dict:
    key = _mafra_key()
    if not key:
        return {"error": "MAFRA/AGROMARKET key not configured"}
    loop = asyncio.get_event_loop()
    agg = await loop.run_in_executor(None, _collect_reservoir_sync, key)
    if not agg:
        return {"error": "no reservoir data"}

    async with AsyncSessionLocal() as db:
        stmt = pg_insert(DroughtIndex).values(
            base_ym=agg["base_ym"], date=kst_today(),
            reservoir_rate=agg["reservoir_rate"], rainfall_avg=agg["rainfall_avg"],
            region_count=agg["region_count"],
        ).on_conflict_do_update(
            constraint="uq_drought_index_ym",
            set_={
                "date": kst_today(),
                "reservoir_rate": agg["reservoir_rate"],
                "rainfall_avg": agg["rainfall_avg"],
                "region_count": agg["region_count"],
            },
        )
        await db.execute(stmt)
        await db.commit()
    logger.info("[mafra] drought index %s: reservoir=%s%%", agg["base_ym"], agg["reservoir_rate"])
    return {"status": "ok", **agg}
