"""KAMIS 지역별 도매/소매 가격 수집 — regional_market_price 테이블 upsert.

관리자 엔드포인트(/admin/collect/regional-prices)와 스케줄러(daily_pipeline)가 공용으로 사용.
"""
import asyncio
import logging
from datetime import timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.regional_price import RegionalMarketPrice
from app.timezone import kst_today

logger = logging.getLogger(__name__)

KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"

REGIONAL_MARKETS = {
    "1101": ("서울가락", "서울"), "1201": ("서울강서", "서울"),
    "2100": ("부산엄궁", "부산"), "2400": ("대구북부", "대구"),
    "2500": ("인천삼산", "인천"), "2600": ("광주각화", "광주"),
    "2700": ("대전오정", "대전"), "2800": ("울산",     "울산"),
    "3100": ("수원",     "경기"), "3200": ("원주",     "강원"),
    "3400": ("청주",     "충북"), "3500": ("천안",     "충남"),
    "3600": ("전주",     "전북"), "3700": ("순천",     "전남"),
    "3800": ("포항",     "경북"), "3900": ("창원",     "경남"),
    "4100": ("제주",     "제주"),
}

ITEM_PNO = {
    "cabbage": "28", "radish": "64", "onion": "117", "green_onion": "122", "garlic": "1003",
    "potato": "24", "sweet_potato": "20", "pepper": "81", "tomato": "60", "cucumber": "52",
    "zucchini": "56", "carrot": "74", "spinach": "38", "lettuce": "42", "perilla": "133",
    "watermelon": "46", "chamoe": "48", "fresh_pepper": "96", "sesame": "143",
    "apple": "198", "pear": "204", "grape": "208", "strawberry": "216",
}
PNO_TO_ITEM = {v: k for k, v in ITEM_PNO.items()}


async def _fetch(mc, target_date, sess, api_key):
    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "action": "dailySalesList", "p_cert_key": api_key, "p_cert_id": "5300",
        "p_returntype": "json", "p_startday": date_str, "p_endday": date_str,
        "p_countrycode": mc, "p_convert_kg_yn": "N",
    }
    mname, sido = REGIONAL_MARKETS[mc]
    try:
        r = await sess.get(KAMIS_BASE, params=params)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    grouped: dict = {}
    for row in data.get("price", []):
        pno = str(row.get("productno", ""))
        if pno not in PNO_TO_ITEM:
            continue
        cls = row.get("product_cls_code", "")
        pstr = str(row.get("dpr1", "")).replace(",", "").strip()
        if not pstr or pstr == "-":
            continue
        try:
            price = float(pstr)
        except ValueError:
            continue
        if price <= 0:
            continue
        grouped.setdefault(pno, {})
        if cls == "02":
            grouped[pno]["w"] = price
        elif cls == "01":
            grouped[pno]["r"] = price
    result = []
    for pno, pd_ in grouped.items():
        w = pd_.get("w")
        rv = pd_.get("r")
        if w is None and rv is None:
            continue
        if w is None:
            w = round(rv / 1.35, 0)
        if rv is None:
            rv = round(w * 1.35, 0)
        result.append({
            "item_code": PNO_TO_ITEM[pno], "date": target_date,
            "market_code": mc, "market_name": mname, "sido": sido,
            "wholesale_price": w, "retail_price": rv,
        })
    return result


async def collect_regional_prices(days: int = 7) -> dict:
    """최근 N일 지역별 가격 수집 후 upsert. 자체 DB 세션 사용."""
    api_key = get_settings().kamis_api_key
    if not api_key:
        return {"error": "KAMIS_API_KEY not configured", "rows_saved": 0}

    end_d = kst_today()
    start_d = end_d - timedelta(days=days - 1)
    total_saved = 0

    async with AsyncSessionLocal() as db:
        async with httpx.AsyncClient(timeout=20, verify=False) as sess:
            cur = start_d
            while cur <= end_d:
                tasks = [_fetch(mc, cur, sess, api_key) for mc in REGIONAL_MARKETS]
                batches = await asyncio.gather(*tasks)
                rows_ = [r for b in batches for r in b]
                if rows_:
                    stmt_ = pg_insert(RegionalMarketPrice).values(rows_)
                    stmt_ = stmt_.on_conflict_do_update(
                        constraint="uq_regional_market_price",
                        set_={
                            "market_name": stmt_.excluded.market_name,
                            "sido": stmt_.excluded.sido,
                            "wholesale_price": stmt_.excluded.wholesale_price,
                            "retail_price": stmt_.excluded.retail_price,
                        },
                    )
                    await db.execute(stmt_)
                    await db.commit()
                    total_saved += len(rows_)
                cur += timedelta(days=1)
                await asyncio.sleep(0.3)

    logger.info("[regional] collected %s rows over %s days", total_saved, days)
    return {"status": "ok", "days": days, "rows_saved": total_saved}
