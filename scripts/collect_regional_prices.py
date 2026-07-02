"""
KAMIS 지역별 도매시장 가격 수집 스크립트
- 전국 15개 주요 도매시장에서 각 품목별 도매가 + 소매가 수집
- 결과를 regional_market_price 테이블에 upsert

Usage:
  python scripts/collect_regional_prices.py              # 오늘 날짜
  python scripts/collect_regional_prices.py 2026-07-01  # 특정 날짜
  python scripts/collect_regional_prices.py 2026-06-01 2026-07-01  # 기간
"""
import sys, asyncio, os, httpx
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from app.models.regional_price import RegionalMarketPrice
from app.config import get_settings

# KAMIS 전국 도매시장 코드 → (시장명, 시도)
REGIONAL_MARKETS = {
    "1101": ("서울가락",   "서울"),
    "1201": ("서울강서",   "서울"),
    "2100": ("부산엄궁",   "부산"),
    "2400": ("대구북부",   "대구"),
    "2500": ("인천삼산",   "인천"),
    "2600": ("광주각화",   "광주"),
    "2700": ("대전오정",   "대전"),
    "2800": ("울산",       "울산"),
    "3100": ("수원",       "경기"),
    "3200": ("원주",       "강원"),
    "3400": ("청주",       "충북"),
    "3500": ("천안",       "충남"),
    "3600": ("전주",       "전북"),
    "3700": ("순천",       "전남"),
    "3800": ("포항",       "경북"),
    "3900": ("창원",       "경남"),
    "4100": ("제주",       "제주"),
}

KAMIS_BASE = "https://www.kamis.or.kr/service/price/xml.do"

# productno → item_code 역매핑
ITEM_CODE_MAP = {
    "cabbage":      {"productno": "28"},
    "radish":       {"productno": "64"},
    "onion":        {"productno": "117"},
    "green_onion":  {"productno": "122"},
    "garlic":       {"productno": "1003"},
    "potato":       {"productno": "24"},
    "sweet_potato": {"productno": "20"},
    "pepper":       {"productno": "81"},
    "tomato":       {"productno": "60"},
    "cucumber":     {"productno": "52"},
    "zucchini":     {"productno": "56"},
    "carrot":       {"productno": "74"},
    "spinach":      {"productno": "38"},
    "lettuce":      {"productno": "42"},
    "perilla":      {"productno": "133"},
    "watermelon":   {"productno": "46"},
    "chamoe":       {"productno": "48"},
    "fresh_pepper": {"productno": "96"},
    "sesame":       {"productno": "143"},
    "apple":        {"productno": "198"},
    "pear":         {"productno": "204"},
    "grape":        {"productno": "208"},     # 포도
    "strawberry":   {"productno": "216"},     # 딸기
}

_PNO_TO_CODE = {v["productno"]: k for k, v in ITEM_CODE_MAP.items()}


async def fetch_market_prices(market_code: str, target_date: date, api_key: str) -> list[dict]:
    """특정 도매시장 하루 전 품목 가격 조회 — 도매(02) + 소매(01) 둘 다 수집"""
    date_str = target_date.strftime("%Y-%m-%d")
    params = {
        "action": "dailySalesList",
        "p_cert_key": api_key,
        "p_cert_id": "5300",
        "p_returntype": "json",
        "p_startday": date_str,
        "p_endday": date_str,
        "p_countrycode": market_code,
        "p_convert_kg_yn": "N",
    }
    market_name, sido = REGIONAL_MARKETS[market_code]

    try:
        async with httpx.AsyncClient(timeout=20, verify=False) as client:
            r = await client.get(KAMIS_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"  [SKIP] {market_name}({market_code}) 요청 실패: {e}")
        return []

    prices = data.get("price", [])
    if not prices:
        return []

    # productno 별로 도매/소매 가격 모으기
    grouped: dict[str, dict] = {}  # productno → {wholesale, retail}
    for row in prices:
        pno = str(row.get("productno", ""))
        if pno not in _PNO_TO_CODE:
            continue
        cls = row.get("product_cls_code", "")
        price_str = str(row.get("dpr1", "")).replace(",", "").strip()
        if not price_str or price_str in ("-", ""):
            continue
        try:
            price = float(price_str)
        except ValueError:
            continue
        if price <= 0:
            continue

        if pno not in grouped:
            grouped[pno] = {}
        if cls == "02":
            grouped[pno]["wholesale"] = price
        elif cls == "01":
            grouped[pno]["retail"] = price

    results = []
    for pno, pdata in grouped.items():
        item_code = _PNO_TO_CODE[pno]
        w = pdata.get("wholesale")
        r = pdata.get("retail")
        if w is None and r is None:
            continue
        # 한쪽만 있으면 추정
        if w is None:
            w = round(r / 1.35, 0)
        if r is None:
            r = round(w * 1.35, 0)
        results.append({
            "item_code": item_code,
            "date": target_date,
            "market_code": market_code,
            "market_name": market_name,
            "sido": sido,
            "wholesale_price": w,
            "retail_price": r,
        })
    return results


async def collect_day(target_date: date, api_key: str) -> list[dict]:
    """전체 지역 시장 하루치 병렬 수집"""
    tasks = [
        fetch_market_prices(mc, target_date, api_key)
        for mc in REGIONAL_MARKETS
    ]
    results_nested = await asyncio.gather(*tasks)
    rows = [row for batch in results_nested for row in batch]
    print(f"  {target_date} — {len(rows)}건 수집 ({len(REGIONAL_MARKETS)}개 시장)")
    return rows


async def upsert_rows(engine, rows: list[dict]):
    """regional_market_price 테이블에 upsert"""
    if not rows:
        return 0
    async with engine.begin() as conn:
        stmt = pg_insert(RegionalMarketPrice).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_regional_market_price",
            set_={
                "market_name":      stmt.excluded.market_name,
                "sido":             stmt.excluded.sido,
                "wholesale_price":  stmt.excluded.wholesale_price,
                "retail_price":     stmt.excluded.retail_price,
            }
        )
        await conn.execute(stmt)
    return len(rows)


async def ensure_table(engine):
    """테이블이 없으면 생성"""
    from app.database import Base
    from app.models import regional_price  # noqa — register model
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main():
    settings = get_settings()
    api_key = settings.kamis_api_key
    if not api_key:
        print("KAMIS_API_KEY 없음 — 종료")
        return

    db_url = settings.database_url
    if not db_url:
        print("DATABASE_URL 없음 — 종료")
        return
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # 날짜 범위 파싱
    args = sys.argv[1:]
    if len(args) >= 2:
        start_d = date.fromisoformat(args[0])
        end_d   = date.fromisoformat(args[1])
    elif len(args) == 1:
        start_d = end_d = date.fromisoformat(args[0])
    else:
        start_d = end_d = date.today()

    print(f"수집 기간: {start_d} ~ {end_d}")
    engine = create_async_engine(db_url, echo=False)
    await ensure_table(engine)

    total = 0
    current = start_d
    while current <= end_d:
        rows = await collect_day(current, api_key)
        n = await upsert_rows(engine, rows)
        total += n
        current += timedelta(days=1)
        if current <= end_d:
            await asyncio.sleep(0.5)  # 과도한 요청 방지

    await engine.dispose()
    print(f"\n완료 — 총 {total}건 저장")


if __name__ == "__main__":
    asyncio.run(main())
