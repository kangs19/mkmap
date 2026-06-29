"""
KOSIS (통계청 국가통계포털) 농업통계 수집기
재배면적 + 생산량 → 가격 예측 feature로 활용

API: https://kosis.kr/openapi/Param/statisticsParamData.do
인증키: Base64 인코딩된 키 그대로 사용
"""
import httpx
import asyncio
from datetime import date
from typing import Optional
from app.config import get_settings

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParamData.do"

# KOSIS 통계표 ID — 농작물 생산조사
# 품목별 재배면적 및 생산량 (연간)
STAT_TABLE = {
    # orgId: 통계청(101), tblId: 농작물생산조사
    "cabbage":     {"orgId": "101", "tblId": "DT_1ET0289", "item_name": "배추"},
    "radish":      {"orgId": "101", "tblId": "DT_1ET0289", "item_name": "무"},
    "onion":       {"orgId": "101", "tblId": "DT_1ET0289", "item_name": "양파"},
    "green_onion": {"orgId": "101", "tblId": "DT_1ET0289", "item_name": "파"},
    "garlic":      {"orgId": "101", "tblId": "DT_1ET0289", "item_name": "마늘"},
}

# 전국 + 주요 시도 코드
REGION_CODES = {
    "전국":  "00",
    "경기":  "41",
    "강원":  "42",
    "충북":  "43",
    "충남":  "44",
    "전북":  "45",
    "전남":  "46",
    "경북":  "47",
    "경남":  "48",
}


async def fetch_crop_production(
    item_code: str,
    year: int,
) -> Optional[dict]:
    """품목별 연간 재배면적 + 생산량 조회"""
    settings = get_settings()
    if not settings.kosis_api_key:
        return None

    tbl = STAT_TABLE.get(item_code)
    if not tbl:
        return None

    params = {
        "method": "getList",
        "apiKey": settings.kosis_api_key,
        "itmId": "T10+T20",       # T10=재배면적, T20=생산량
        "objL1": "ALL",            # 품목 전체
        "objL2": "ALL",            # 지역 전체
        "format": "json",
        "jsonVD": "Y",
        "prdSe": "Y",             # 연간
        "startPrdDe": str(year),
        "endPrdDe": str(year),
        "orgId": tbl["orgId"],
        "tblId": tbl["tblId"],
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(KOSIS_BASE, params=params)
                r.raise_for_status()
                data = r.json()
            return _parse_production(data, item_code, tbl["item_name"], year)
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(1)
    return None


async def fetch_recent_production(item_code: str, years: int = 3) -> list[dict]:
    """최근 N년치 생산 통계 수집"""
    results = []
    current_year = date.today().year
    # 통계청은 전년도까지만 확정 발표
    for yr in range(current_year - years, current_year):
        row = await fetch_crop_production(item_code, yr)
        if row:
            results.append(row)
        await asyncio.sleep(0.5)
    return results


async def fetch_all_crops_production(years: int = 3) -> dict:
    """전 품목 생산통계 수집"""
    result = {}
    for item_code in STAT_TABLE:
        rows = await fetch_recent_production(item_code, years)
        result[item_code] = rows
    return result


def _parse_production(data, item_code: str, item_name: str, year: int) -> Optional[dict]:
    """KOSIS 응답 파싱 → 전국 재배면적/생산량 추출"""
    try:
        if not isinstance(data, list):
            return None

        area_ha = None
        production_ton = None

        for row in data:
            # 품목명 필터
            nm = row.get("C1_NM", "") or row.get("ITM_NM", "")
            if item_name not in nm:
                continue

            # 전국 데이터
            region = row.get("C2_NM", "") or ""
            if "전국" not in region and region != "":
                continue

            itm = row.get("ITM_NM", "")
            try:
                val = float(str(row.get("DT", "0")).replace(",", ""))
            except (ValueError, TypeError):
                continue

            if "재배면적" in itm or "면적" in itm:
                area_ha = val
            elif "생산량" in itm or "수확량" in itm:
                production_ton = val

        if area_ha is None and production_ton is None:
            return None

        return {
            "item_code": item_code,
            "year": year,
            "area_ha": area_ha,
            "production_ton": production_ton,
            "source": "kosis",
        }
    except Exception:
        return None


async def get_production_feature(item_code: str) -> dict:
    """파이프라인 피처용: 가장 최근 확정 생산량 반환"""
    current_year = date.today().year
    for yr in range(current_year - 1, current_year - 4, -1):
        row = await fetch_crop_production(item_code, yr)
        if row and (row.get("production_ton") or row.get("area_ha")):
            return row
    return {}
