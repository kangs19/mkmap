"""
KAMIS (농산물유통정보) 도매가격 수집기
API: https://www.kamis.or.kr/customer/reference/openapi_list.do
"""
import httpx
import asyncio
from datetime import date, timedelta
from typing import Optional
from app.config import get_settings

KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"

# 품목코드 (KAMIS 기준)
ITEM_CODE_MAP = {
    "cabbage":     ("100", "배추",  "10kg"),
    "radish":      ("200", "무",    "20kg"),
    "onion":       ("222", "양파",  "20kg"),
    "green_onion": ("214", "대파",  "1kg"),
    "garlic":      ("100", "마늘",  "10kg"),  # 깐마늘 기준
}

# 마늘은 별도 itemCategoryCode
GARLIC_ITEM_CODE = "211"

# 경락가격(가락시장) 조회 action
ACTION_DAILY = "dailySalesList"

# 지역코드 (가락시장=1101)
MARKET_CODE = "1101"


async def fetch_daily_price(
    item_code: str,
    target_date: date,
    retries: int = 3,
) -> Optional[dict]:
    """KAMIS 일별 도매가격 1건 조회"""
    settings = get_settings()
    if not settings.kamis_api_key:
        return None

    code_map = ITEM_CODE_MAP.get(item_code)
    if not code_map:
        return None

    kamis_code, item_name, unit = code_map
    if item_code == "garlic":
        kamis_code = GARLIC_ITEM_CODE

    date_str = target_date.strftime("%Y-%m-%d")

    params = {
        "action": ACTION_DAILY,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",  # KAMIS 공개 cert_id
        "p_returntype": "json",
        "p_startday": date_str,
        "p_endday": date_str,
        "p_itemcategorycode": "100" if item_code != "garlic" else "100",
        "p_itemcode": kamis_code,
        "p_kindcode": "01",
        "p_productrankcode": "04",  # 상품
        "p_countrycode": MARKET_CODE,
        "p_convert_kg_yn": "N",
    }

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(KAMIS_BASE, params=params)
                r.raise_for_status()
                data = r.json()

            # 응답 파싱
            price = _parse_response(data, item_code, target_date, unit)
            return price
        except Exception:
            if attempt == retries - 1:
                return None
            await asyncio.sleep(1)

    return None


async def fetch_price_range(
    item_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """기간별 일별 도매가격 수집 (날짜별 순차 요청)"""
    settings = get_settings()
    if not settings.kamis_api_key:
        return []

    code_map = ITEM_CODE_MAP.get(item_code)
    if not code_map:
        return []

    kamis_code, item_name, unit = code_map
    if item_code == "garlic":
        kamis_code = GARLIC_ITEM_CODE

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    params = {
        "action": ACTION_DAILY,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": start_str,
        "p_endday": end_str,
        "p_itemcategorycode": "100",
        "p_itemcode": kamis_code,
        "p_kindcode": "01",
        "p_productrankcode": "04",
        "p_countrycode": MARKET_CODE,
        "p_convert_kg_yn": "N",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(KAMIS_BASE, params=params)
            r.raise_for_status()
            data = r.json()
        return _parse_range_response(data, item_code, unit)
    except Exception:
        return []


def _parse_response(data: dict, item_code: str, target_date: date, unit: str) -> Optional[dict]:
    try:
        items = data.get("data", {}).get("item", [])
        if not items:
            return None
        row = items[0]
        price_str = row.get("dpr1", "0").replace(",", "").strip()
        if not price_str or price_str == "-":
            return None
        price = float(price_str)
        if price <= 0:
            return None
        return {
            "item_code": item_code,
            "date": target_date,
            "market": "가락시장",
            "grade": "상품",
            "wholesale_price": price,
            "retail_price": round(price * 1.35, 0),
            "avg_year_price": float(row.get("dpr5", 0).replace(",", "") or 0),
            "prev_year_price": float(row.get("dpr6", 0).replace(",", "") or 0),
            "source": "kamis",
        }
    except Exception:
        return None


def _parse_range_response(data: dict, item_code: str, unit: str) -> list[dict]:
    results = []
    try:
        items = data.get("data", {}).get("item", [])
        for row in items:
            date_str = row.get("yyyy", "") + "-" + row.get("regday", "").replace("/", "-")
            try:
                d = date.fromisoformat(date_str)
            except Exception:
                continue
            price_str = row.get("dpr1", "0").replace(",", "").strip()
            if not price_str or price_str == "-":
                continue
            try:
                price = float(price_str)
            except Exception:
                continue
            if price <= 0:
                continue

            def safe_float(v):
                try:
                    return float(str(v).replace(",", "") or 0)
                except Exception:
                    return 0.0

            results.append({
                "item_code": item_code,
                "date": d,
                "market": "가락시장",
                "grade": "상품",
                "wholesale_price": price,
                "retail_price": round(price * 1.35, 0),
                "avg_year_price": safe_float(row.get("dpr5", 0)),
                "prev_year_price": safe_float(row.get("dpr6", 0)),
                "source": "kamis",
            })
    except Exception:
        pass
    return results
