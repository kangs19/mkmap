"""
KAMIS (농산물유통정보) 도매가격 수집기
API: https://www.kamis.or.kr/customer/reference/openapi_list.do

응답 구조: data["price"] 배열, product_cls_code="02" 가 도매
품목 식별: productno 필드로 필터링 (p_itemcode 파라미터는 필터 효과 없음)
"""
import httpx
import asyncio
from datetime import date, timedelta
from typing import Optional
from app.config import get_settings

KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"

# 품목별 KAMIS 코드 — productno 는 도매(cls=02) 기준 실측값
ITEM_CODE_MAP = {
    "cabbage":     {"productno": "28",   "name": "배추",  "unit": "10kg",  "category": "200"},
    "radish":      {"productno": "64",   "name": "무",    "unit": "20kg",  "category": "200"},
    "onion":       {"productno": "117",  "name": "양파",  "unit": "20kg",  "category": "200"},
    "green_onion": {"productno": "122",  "name": "대파",  "unit": "1kg",   "category": "200"},
    "garlic":      {"productno": "1003", "name": "마늘",  "unit": "10kg",  "category": "200"},
}

ACTION_DAILY  = "dailySalesList"
ACTION_PERIOD = "periodSaleList"
MARKET_CODE   = "1101"  # 가락시장


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

    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "action": ACTION_DAILY,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": date_str,
        "p_endday": date_str,
        "p_countrycode": MARKET_CODE,
        "p_convert_kg_yn": "N",
    }

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(KAMIS_BASE, params=params)
                r.raise_for_status()
                data = r.json()
            return _parse_response(data, item_code, target_date, code_map)
        except Exception:
            if attempt == retries - 1:
                return None
            await asyncio.sleep(1)
    return None


async def fetch_all_prices_for_date(target_date: date) -> dict[str, dict]:
    """dailySalesList로 특정 날짜의 전 품목 도매가 한번에 수집.
    반환: {item_code: price_row_dict}
    """
    settings = get_settings()
    if not settings.kamis_api_key:
        return {}

    params = {
        "action": ACTION_DAILY,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": target_date.strftime("%Y-%m-%d"),
        "p_endday": target_date.strftime("%Y-%m-%d"),
        "p_countrycode": MARKET_CODE,
        "p_convert_kg_yn": "N",
    }

    # productno → item_code 역매핑
    pno_to_item = {v["productno"]: k for k, v in ITEM_CODE_MAP.items()}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(KAMIS_BASE, params=params)
            r.raise_for_status()
            data = r.json()

        result = {}
        for row in data.get("price", []):
            if row.get("product_cls_code") != "02":
                continue
            item_code = pno_to_item.get(str(row.get("productno", "")))
            if not item_code:
                continue
            code_map = ITEM_CODE_MAP[item_code]
            parsed = _parse_response({"price": [row]}, item_code, target_date, code_map)
            if parsed:
                result[item_code] = parsed
        return result
    except Exception:
        return {}


async def fetch_price_range(
    item_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """기간별 일별 도매가격 — dailySalesList 날짜별 반복 (안정적)"""
    settings = get_settings()
    if not settings.kamis_api_key:
        return []

    results = []
    current = start_date
    while current <= end_date:
        day_data = await fetch_all_prices_for_date(current)
        if item_code in day_data:
            results.append(day_data[item_code])
        current += timedelta(days=1)
        await asyncio.sleep(0.2)
    return results


def _parse_response(data: dict, item_code: str, target_date: date, code_map: dict) -> Optional[dict]:
    """dailySalesList 응답 파싱 — price 배열에서 도매(02) + productno 필터링"""
    try:
        prices = data.get("price", [])
        if not prices:
            return None

        productno = code_map["productno"]
        for row in prices:
            if row.get("product_cls_code") != "02":
                continue
            if str(row.get("productno", "")) != productno:
                continue

            price_str = str(row.get("dpr1", "0")).replace(",", "").strip()
            if not price_str or price_str == "-":
                continue
            price = float(price_str)
            if price <= 0:
                continue

            def _sf(v):
                try:
                    return float(str(v).replace(",", "") or 0)
                except Exception:
                    return 0.0

            return {
                "item_code": item_code,
                "date": target_date,
                "market": "가락시장",
                "grade": "상품",
                "wholesale_price": price,
                "retail_price": round(price * 1.35, 0),
                "avg_year_price": _sf(row.get("dpr5", 0)),
                "prev_year_price": _sf(row.get("dpr6", 0)),
                "source": "kamis",
            }
    except Exception:
        pass
    return None


