"""지역별 도매가 수집 — 도매시장 통합홈페이지 실시간 경락 API (api.agromarket.kr).

전국 공영도매시장의 실시간 경매 낙찰가(scsbd_prc)를 도매시장별로 집계해
regional_market_price 테이블에 upsert. 시장(=지역)별로 실제 다른 가격을 제공한다.

관리자 엔드포인트(/admin/collect/regional-prices)와 스케줄러(daily_pipeline)가 공용 사용.
운영 사용을 위해 Railway 환경변수 AGROMARKET_API_KEY 설정 필요.
"""
import asyncio
import json
import logging
import ssl
import statistics
import urllib.parse
import urllib.request
from datetime import timedelta

from sqlalchemy import func as sqlfunc, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.regional_price import RegionalMarketPrice
from app.timezone import kst_today

logger = logging.getLogger(__name__)

AGROMARKET_EP = "https://api.agromarket.kr/api/katRealTime/v2/trades"
_SSL_CTX = ssl.create_default_context()

# 우리 5개 작물 → 경락 데이터 필터 (필드, 연산자, 값)
CROP_FILTER = {
    "cabbage":     ("gds_mclsf_nm", "EQ", "배추"),
    "radish":      ("gds_mclsf_nm", "EQ", "무"),
    "onion":       ("gds_mclsf_nm", "EQ", "양파"),
    "garlic":      ("gds_mclsf_nm", "EQ", "마늘"),
    "green_onion": ("corp_gds_item_nm", "LIKE", "대파"),
}

# 도매시장명 → 시도 (도시 키워드 기반, 신규 시장에도 대응)
_SIDO_KEYWORDS = [
    (("가락", "강서"), "서울"),
    (("엄궁", "반여", "국제", "부산"), "부산"),
    (("대구", "북부"), "대구"),
    (("삼산", "남촌", "인천"), "인천"),
    (("각화", "서부", "광주"), "광주"),
    (("오정", "노은", "대전"), "대전"),
    (("울산",), "울산"),
    (("안양", "구리", "안산", "수원", "부천", "안성", "성남"), "경기"),
    (("춘천", "원주", "강릉"), "강원"),
    (("청주", "충주"), "충북"),
    (("천안", "논산"), "충남"),
    (("전주", "익산", "정읍"), "전북"),
    (("순천", "목포", "여수"), "전남"),
    (("안동", "포항", "구미", "김천"), "경북"),
    (("진주", "창원", "마산", "김해", "통영"), "경남"),
    (("제주", "서귀포"), "제주"),
]


def _sido_of(market_name: str) -> str:
    for keywords, sido in _SIDO_KEYWORDS:
        if any(k in market_name for k in keywords):
            return sido
    return "기타"


def _fetch_page(api_key: str, date_str: str, filt: tuple, page: int, rows: int = 1000) -> dict:
    field, op, val = filt
    params = {
        "serviceKey": api_key,
        "cond[trd_clcln_ymd::EQ]": date_str,
        f"cond[{field}::{op}]": val,
        "numOfRows": str(rows),
        "pageNo": str(page),
    }
    url = f"{AGROMARKET_EP}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def _collect_crop_sync(api_key: str, date_str: str, item_code: str, filt: tuple, max_pages: int = 12) -> dict:
    """한 작물의 시장별 중앙값 kg당 도매가 계산 (blocking; executor에서 실행)."""
    per_market: dict[str, list] = {}
    market_name: dict[str, str] = {}
    page = 1
    while page <= max_pages:
        try:
            data = _fetch_page(api_key, date_str, filt, page)
        except Exception as exc:
            logger.warning("[regional] fetch fail %s p%s: %s", item_code, page, exc)
            break
        body = data.get("response", {}).get("body", {})
        items = body.get("items", {})
        rows = items.get("item") if isinstance(items, dict) else None
        if not rows:
            break
        if not isinstance(rows, list):
            rows = [rows]
        for it in rows:
            unit_nm = (it.get("unit_nm") or "").lower()
            if unit_nm != "kg":
                continue
            try:
                prc = float(it["scsbd_prc"])
                uq = float(it.get("unit_qty") or 0)
            except (ValueError, TypeError, KeyError):
                continue
            if uq <= 0 or prc <= 0:
                continue
            per_kg = prc / uq
            # 비정상 이상치 컷 (kg당 100원 미만 / 100,000원 초과 제외)
            if per_kg < 100 or per_kg > 100000:
                continue
            mc = it.get("whsl_mrkt_cd")
            if not mc:
                continue
            per_market.setdefault(mc, []).append(per_kg)
            market_name[mc] = it.get("whsl_mrkt_nm", mc)
        total = int(body.get("totalCount", 0) or 0)
        if page * 1000 >= total:
            break
        page += 1

    result = {}
    for mc, prices in per_market.items():
        # 표본이 너무 적은 시장은 제외 (중앙값 왜곡 방지)
        if len(prices) < 3:
            continue
        w = round(statistics.median(prices))
        result[mc] = {
            "market_name": market_name.get(mc, mc),
            "sido": _sido_of(market_name.get(mc, "")),
            "wholesale_price": float(w),
            "retail_price": float(round(w * 1.35)),  # 경락엔 소매 없음 → 추정
        }
    return result


async def collect_regional_prices(days: int = 3) -> dict:
    """최근 N일 지역별 도매가 수집 후 upsert. 자체 DB 세션 사용."""
    api_key = get_settings().agromarket_api_key
    if not api_key:
        return {"error": "AGROMARKET_API_KEY not configured", "rows_saved": 0}

    end_d = kst_today()
    total_saved = 0
    loop = asyncio.get_event_loop()

    async with AsyncSessionLocal() as db:
        # 구 KAMIS 형식(4자리 시장코드, 전국 동일값) 잔존 행 1회 정리
        await db.execute(
            delete(RegionalMarketPrice).where(
                sqlfunc.length(RegionalMarketPrice.market_code) < 6
            )
        )
        await db.commit()

        for day_off in range(days):
            target = end_d - timedelta(days=day_off)
            date_str = target.strftime("%Y-%m-%d")
            for item_code, filt in CROP_FILTER.items():
                agg = await loop.run_in_executor(
                    None, _collect_crop_sync, api_key, date_str, item_code, filt
                )
                rows_ = [
                    {
                        "item_code": item_code, "date": target,
                        "market_code": mc, "market_name": v["market_name"],
                        "sido": v["sido"], "wholesale_price": v["wholesale_price"],
                        "retail_price": v["retail_price"],
                    }
                    for mc, v in agg.items()
                ]
                if not rows_:
                    continue
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

    logger.info("[regional] agromarket collected %s rows over %s days", total_saved, days)
    return {"status": "ok", "days": days, "rows_saved": total_saved, "source": "agromarket"}
