"""
KAMIS 도매시장 거래량/반입량 수집기

API action: selectWhsalPriceList (도매시장 거래현황)
반환: 일별 거래량(kg), 거래금액, 반입량
"""
import httpx
import asyncio
from datetime import date, timedelta
from typing import Optional
from app.config import get_settings
from app.collectors.kamis import ITEM_CODE_MAP, MARKET_CODE

KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"

# 거래현황 조회 action
ACTION_MARKET = "periodSaleList"


async def fetch_market_volume(
    item_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """KAMIS 도매시장 기간별 거래현황 수집"""
    settings = get_settings()
    if not settings.kamis_api_key:
        return []

    code_map = ITEM_CODE_MAP.get(item_code)
    if not code_map:
        return []

    params = {
        "action": ACTION_MARKET,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": start_date.strftime("%Y-%m-%d"),
        "p_endday": end_date.strftime("%Y-%m-%d"),
        "p_itemcategorycode": code_map["category"],
        "p_itemcode": code_map["item"],
        "p_kindcode": "01",
        "p_productrankcode": "04",
        "p_countrycode": MARKET_CODE,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(KAMIS_BASE, params=params)
                r.raise_for_status()
                data = r.json()
            return _parse_market_response(data, item_code)
        except Exception:
            if attempt == 2:
                return []
            await asyncio.sleep(1)
    return []


def _parse_market_response(data: dict, item_code: str) -> list[dict]:
    results = []
    try:
        items = data.get("data", {}).get("item", [])
        if not items:
            return []

        for row in items:
            # 날짜 파싱
            yyyy = row.get("yyyy", "")
            regday = row.get("regday", "").replace("/", "-")
            date_str = f"{yyyy}-{regday}" if yyyy else regday
            try:
                d = date.fromisoformat(date_str)
            except Exception:
                continue

            def safe_float(v, default=None):
                try:
                    s = str(v).replace(",", "").strip()
                    return float(s) if s and s != "-" else default
                except Exception:
                    return default

            # 거래량·반입량 필드 (KAMIS 응답 필드명)
            volume_kg    = safe_float(row.get("qty"))       # 거래량(kg)
            trade_amount = safe_float(row.get("amount"))    # 거래금액(천원)
            supply_vol   = safe_float(row.get("supply"))    # 반입량(kg)

            if volume_kg is None and supply_vol is None:
                continue

            results.append({
                "item_code":    item_code,
                "date":         d,
                "market":       "가락시장",
                "origin_region": None,
                "volume_kg":    volume_kg,
                "trade_volume": volume_kg,
                "trade_amount": trade_amount,
                "source":       "kamis",
            })
    except Exception:
        pass
    return results
