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


async def fetch_price_range(
    item_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """기간별 일별 도매가격 수집 (periodSaleList)"""
    settings = get_settings()
    if not settings.kamis_api_key:
        return []

    code_map = ITEM_CODE_MAP.get(item_code)
    if not code_map:
        return []

    params = {
        "action": ACTION_PERIOD,
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": start_date.strftime("%Y-%m-%d"),
        "p_endday": end_date.strftime("%Y-%m-%d"),
        "p_itemcategorycode": code_map["category"],
        "p_itemcode": code_map["productno"],
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
        return _parse_range_response(data, item_code, code_map)
    except Exception:
        return []


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


def _parse_range_response(data: dict, item_code: str, code_map: dict) -> list[dict]:
    """periodSaleList 응답 파싱"""
    results = []
    try:
        # periodSaleList 는 data.item 구조를 사용
        items = data.get("data", {}).get("item", [])
        if not items:
            # fallback: price 배열 구조
            items = data.get("price", [])

        productno = code_map["productno"]
        for row in items:
            # product_cls_code 있으면 도매 필터
            if "product_cls_code" in row and row.get("product_cls_code") != "02":
                # productno 도 체크
                if str(row.get("productno", "")) != productno:
                    continue

            yyyy = row.get("yyyy", "")
            regday = row.get("regday", "").replace("/", "-")
            if yyyy and regday:
                date_str = f"{yyyy}-{regday}"
            else:
                date_str = row.get("lastest_day", "")
            try:
                d = date.fromisoformat(date_str)
            except Exception:
                continue

            price_str = str(row.get("dpr1", "0")).replace(",", "").strip()
            if not price_str or price_str == "-":
                continue
            try:
                price = float(price_str)
            except Exception:
                continue
            if price <= 0:
                continue

            def _sf(v):
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
                "avg_year_price": _sf(row.get("dpr5", 0)),
                "prev_year_price": _sf(row.get("dpr6", 0)),
                "source": "kamis",
            })
    except Exception:
        pass
    return results
