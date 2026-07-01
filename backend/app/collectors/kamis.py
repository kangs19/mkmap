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


# periodProductList 메타데이터 — config/external_mappings/kamis_price_mapping.csv 기준
# itemcode/kindcode 검증: 봄 품종(01)이 30일 기준 가장 많은 데이터 보유
_PERIOD_PRODUCT_META = {
    "cabbage":     {"p_itemcategorycode": "200", "p_itemcode": "211", "p_kindcode": "01", "p_productrankcode": "04"},
    "radish":      {"p_itemcategorycode": "200", "p_itemcode": "231", "p_kindcode": "01", "p_productrankcode": "04"},
    "onion":       {"p_itemcategorycode": "200", "p_itemcode": "245", "p_kindcode": "00", "p_productrankcode": "04"},
    "green_onion": {"p_itemcategorycode": "200", "p_itemcode": "246", "p_kindcode": "00", "p_productrankcode": "04"},
    "garlic":      {"p_itemcategorycode": "200", "p_itemcode": "258", "p_kindcode": "03", "p_productrankcode": "04"},
}

# periodProductList 가격 단위 보정 계수 (ITEM_CODE_MAP 단위 기준으로 맞춤)
# 마늘 kindcode=03(깐마늘,국산)은 1kg 단위로 반환 → 기존 DB 데이터(10kg)와 단위 일치를 위해 10 곱함
# 배추(01)/무(01)/양파(00)/대파(00)는 각 ITEM_CODE_MAP 단위(10kg/20kg/20kg/1kg)와 일치하는지
# 실제 API 응답 기준으로 주기적 검증 필요 (KAMIS periodProductList 단위는 품종코드별로 상이할 수 있음)
_PERIOD_UNIT_MULTIPLIER: dict[str, float] = {
    "garlic": 10.0,
}


async def fetch_period_prices(
    item_code: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """periodProductList로 기간별 날짜별 소매가격 수집 (httpx — SSL 우회 포함).

    dailySalesList는 날짜 파라미터를 무시해 change_30d_pct가 항상 0.0이 되는 버그가 있다.
    periodProductList는 p_startday~p_endday 범위의 날짜별 가격 배열을 반환한다.
    wholesale_price가 없으면 retail_price를 사용.
    """
    settings = get_settings()
    if not settings.kamis_api_key:
        return []

    meta = _PERIOD_PRODUCT_META.get(item_code)
    if not meta:
        return []

    params = {
        "action": "periodProductList",
        "p_cert_key": settings.kamis_api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": start_date.isoformat(),
        "p_endday": end_date.isoformat(),
        "p_countrycode": MARKET_CODE,
        "p_convert_kg_yn": "N",
        **meta,
    }

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.get(KAMIS_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []

    results = []
    try:
        items = data.get("data", {}).get("item", [])
        for entry in items:
            regday = entry.get("regday", "")  # 예: "07/01"
            yyyy = entry.get("yyyy", str(end_date.year))
            price_str = str(entry.get("price", "0")).replace(",", "").strip()
            if not price_str or price_str in ("-", ""):
                continue
            try:
                price = float(price_str)
            except ValueError:
                continue
            if price <= 0:
                continue

            if regday and "/" in regday:
                mm, dd = regday.split("/")
                try:
                    mm_int, dd_int, yyyy_int = int(mm), int(dd), int(yyyy)
                    row_date = date(yyyy_int, mm_int, dd_int)
                    # 미래 날짜면 전년도로 보정 (연초 요청 시 전년 12월 데이터가 섞이는 경우)
                    if row_date > end_date:
                        row_date = date(yyyy_int - 1, mm_int, dd_int)
                except (ValueError, OverflowError):
                    continue
            else:
                continue

            multiplier = _PERIOD_UNIT_MULTIPLIER.get(item_code, 1.0)
            adj_price = round(price * multiplier, 0)
            results.append({
                "item_code": item_code,
                "date": row_date,
                "market": "가락시장",
                "grade": "상품",
                "wholesale_price": adj_price,
                "retail_price": round(adj_price * 1.35, 0),
                "source": "kamis",
            })
    except Exception:
        pass

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


