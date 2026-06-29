"""
품목별 메타데이터 빌더
KAMIS 가격 + KOSIS 생산 + KMA 기상 실데이터로 피처 집계 → ItemMeta 갱신

호출: await build_all_meta(db)
"""
import asyncio
import math
from datetime import date, timedelta
from typing import Optional
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meta import ItemMeta
from app.models.price import DailyPrice
from app.models.production import CropProduction
from app.models.weather import DailyWeather
from app.collectors.kamis import ITEM_CODE_MAP

logger = logging.getLogger("meta_builder")

# 품목별 주산지 region_code (KMA 관측소)
ITEM_MAIN_REGION = {
    "cabbage":     {"code": "KR-46", "name": "전남(해남)"},   # 배추 주산지
    "radish":      {"code": "KR-46", "name": "전남(무안)"},   # 무 주산지
    "onion":       {"code": "KR-46", "name": "전남(무안)"},   # 양파 주산지
    "green_onion": {"code": "KR-41", "name": "경기(수원)"},   # 대파
    "garlic":      {"code": "KR-47", "name": "경북(의성)"},   # 마늘 주산지
}

# 품목 기본 정보
ITEM_INFO = {
    "cabbage":     {"name": "배추",  "category": "채소류", "unit": "10kg"},
    "radish":      {"name": "무",    "category": "채소류", "unit": "20kg"},
    "onion":       {"name": "양파",  "category": "채소류", "unit": "20kg"},
    "green_onion": {"name": "대파",  "category": "채소류", "unit": "1kg"},
    "garlic":      {"name": "마늘",  "category": "채소류", "unit": "10kg"},
}


async def build_all_meta(db: AsyncSession) -> dict:
    """전 품목 메타데이터 빌드 + DB 갱신"""
    results = {}
    for item_code in ITEM_CODE_MAP:
        try:
            meta = await build_item_meta(db, item_code)
            await _upsert_meta(db, item_code, meta)
            results[item_code] = {"status": "ok", "confidence": meta.get("confidence", "draft")}
            logger.info(f"[meta] {item_code}: {meta.get('confidence')} | price={meta.get('price_today')} | risk={meta.get('risk_level')}")
        except Exception as e:
            logger.error(f"[meta] {item_code} 실패: {e}", exc_info=True)
            results[item_code] = {"status": "error", "error": str(e)}
    await db.commit()
    return results


async def build_item_meta(db: AsyncSession, item_code: str) -> dict:
    """품목 1개 메타데이터 피처 계산"""
    today = date.today()

    # 병렬 데이터 수집
    price_rows, prod_rows, weather_rows = await asyncio.gather(
        _fetch_price_history(db, item_code, days=400),
        _fetch_production(db, item_code),
        _fetch_weather(db, item_code, days=30),
    )

    meta = {}
    info = ITEM_INFO.get(item_code, {})
    code_map = ITEM_CODE_MAP.get(item_code, {})
    region_info = ITEM_MAIN_REGION.get(item_code, {})

    # ── 기본 정보 ─────────────────────────────────────────────────────────
    meta["item_name"]      = info.get("name", item_code)
    meta["kamis_productno"] = code_map.get("productno", "")
    meta["unit"]           = info.get("unit", "")
    meta["category_name"]  = info.get("category", "채소류")
    meta["main_region"]    = region_info.get("name", "")

    # ── 가격 피처 ─────────────────────────────────────────────────────────
    price_feats = _compute_price_features(price_rows, today)
    meta.update(price_feats)

    # ── 생산 피처 ─────────────────────────────────────────────────────────
    prod_feats = _compute_production_features(prod_rows, today)
    meta.update(prod_feats)

    # ── 기상 피처 ─────────────────────────────────────────────────────────
    weather_feats = _compute_weather_features(weather_rows)
    meta.update(weather_feats)

    # ── 종합 위험도 ───────────────────────────────────────────────────────
    risk = _compute_risk(meta)
    meta.update(risk)

    # ── 데이터 메타 ───────────────────────────────────────────────────────
    if price_rows:
        meta["price_data_from"] = str(min(r.date for r in price_rows))
        meta["price_data_to"]   = str(max(r.date for r in price_rows))
        meta["data_days_count"] = len(price_rows)

    # 신뢰도 결정
    has_price = meta.get("price_today") is not None
    has_prod  = meta.get("production_ton_y1") is not None
    has_wthr  = meta.get("weather_temp_avg_7d") is not None
    if has_price and has_prod and has_wthr:
        meta["confidence"] = "full"
    elif has_price and (has_prod or has_wthr):
        meta["confidence"] = "partial"
    elif has_price:
        meta["confidence"] = "price_only"
    else:
        meta["confidence"] = "draft"

    return meta


# ── 가격 피처 계산 ─────────────────────────────────────────────────────────

def _compute_price_features(rows: list, today: date) -> dict:
    if not rows:
        return {}

    # 날짜 → 가격 dict
    price_by_date = {r.date: r.wholesale_price for r in rows if r.wholesale_price}
    sorted_dates = sorted(price_by_date)
    if not sorted_dates:
        return {}

    prices_all   = [price_by_date[d] for d in sorted_dates]
    latest_date  = sorted_dates[-1]
    price_today  = price_by_date[latest_date]

    def window_avg(n_days):
        cutoff = latest_date - timedelta(days=n_days)
        vals = [price_by_date[d] for d in sorted_dates if d >= cutoff]
        return round(sum(vals) / len(vals), 1) if vals else None

    def window_std(n_days):
        cutoff = latest_date - timedelta(days=n_days)
        vals = [price_by_date[d] for d in sorted_dates if d >= cutoff]
        if len(vals) < 2:
            return None
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        return round(math.sqrt(variance), 1)

    avg7  = window_avg(7)
    avg30 = window_avg(30)
    avg90 = window_avg(90)
    std30 = window_std(30)

    # 52주 최고/최저
    cutoff_52w = latest_date - timedelta(weeks=52)
    prices_52w = [price_by_date[d] for d in sorted_dates if d >= cutoff_52w]
    min_52w = min(prices_52w) if prices_52w else None
    max_52w = max(prices_52w) if prices_52w else None

    # 52주 범위 내 현재 위치 (0=최저, 1=최고)
    pct_52w = None
    if min_52w and max_52w and max_52w > min_52w:
        pct_52w = round((price_today - min_52w) / (max_52w - min_52w), 3)

    # 전년 동기 가격 (±15일 평균)
    prev_year_prices = []
    for d in sorted_dates:
        delta = (latest_date.replace(year=latest_date.year - 1) - d).days
        if abs(delta) <= 15:
            prev_year_prices.append(price_by_date[d])
    prev_year = round(sum(prev_year_prices) / len(prev_year_prices), 1) if prev_year_prices else None
    yoy_pct = round((price_today - prev_year) / prev_year * 100, 1) if prev_year else None

    # 모멘텀 (현재가 / N일전 가격)
    def momentum(n_days):
        target = latest_date - timedelta(days=n_days)
        # 가장 가까운 날짜 찾기
        closest = min(sorted_dates, key=lambda d: abs((d - target).days), default=None)
        if closest and abs((closest - target).days) <= 5:
            old_price = price_by_date[closest]
            if old_price and old_price > 0:
                return round(price_today / old_price, 4)
        return None

    mom7  = momentum(7)
    mom30 = momentum(30)

    # MA30 대비 현재가 위치 (%)
    vs_ma30 = round((price_today - avg30) / avg30 * 100, 1) if avg30 else None

    # 30일 추세 기울기 (원/일) — 선형회귀
    slope = _linear_slope(sorted_dates, price_by_date, 30)

    # 계절성 지수 — 현재 월의 과거 동월 평균 / 전체 평균
    seasonal_idx = _seasonal_index(sorted_dates, price_by_date, today.month)

    # 변동계수
    cv30 = round(std30 / avg30, 3) if std30 and avg30 else None

    return {
        "price_today":       round(price_today, 1),
        "price_avg_7d":      avg7,
        "price_avg_30d":     avg30,
        "price_avg_90d":     avg90,
        "price_std_30d":     std30,
        "price_cv_30d":      cv30,
        "price_min_52w":     round(min_52w, 1) if min_52w else None,
        "price_max_52w":     round(max_52w, 1) if max_52w else None,
        "price_pct_of_52w_range": pct_52w,
        "price_prev_year":   prev_year,
        "yoy_change_pct":    yoy_pct,
        "mom_7d":            mom7,
        "mom_30d":           mom30,
        "price_vs_ma30_pct": vs_ma30,
        "trend_slope_30d":   slope,
        "seasonal_index":    seasonal_idx,
    }


def _linear_slope(sorted_dates: list, price_by_date: dict, n_days: int) -> Optional[float]:
    """단순 선형회귀 기울기 (원/일)"""
    if not sorted_dates:
        return None
    latest = sorted_dates[-1]
    cutoff = latest - timedelta(days=n_days)
    pts = [(i, price_by_date[d]) for i, d in enumerate(sorted_dates) if d >= cutoff]
    n = len(pts)
    if n < 3:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x_mean, y_mean = sum(xs) / n, sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return None
    return round(num / den, 2)


def _seasonal_index(sorted_dates: list, price_by_date: dict, target_month: int) -> Optional[float]:
    """계절성 지수 = 동월 평균 / 전체 평균"""
    all_prices = list(price_by_date.values())
    if not all_prices:
        return None
    overall_avg = sum(all_prices) / len(all_prices)
    monthly = [price_by_date[d] for d in sorted_dates if d.month == target_month]
    if not monthly or overall_avg == 0:
        return None
    return round(sum(monthly) / len(monthly) / overall_avg, 3)


# ── 생산 피처 계산 ─────────────────────────────────────────────────────────

def _compute_production_features(rows: list, today: date) -> dict:
    if not rows:
        return {}

    # 연도 내림차순 정렬
    by_year = {r.year: r for r in rows}
    years = sorted(by_year.keys(), reverse=True)
    if not years:
        return {}

    current_year = today.year
    # 통계청은 전년도까지 확정
    y1_year = current_year - 1
    y2_year = current_year - 2
    y3_year = current_year - 3

    def get(y, field):
        row = by_year.get(y)
        return getattr(row, field, None) if row else None

    area_y1 = get(y1_year, "area_ha")
    area_y2 = get(y2_year, "area_ha")
    prod_y1 = get(y1_year, "production_ton")
    prod_y2 = get(y2_year, "production_ton")

    area_yoy = None
    if area_y1 and area_y2 and area_y2 > 0:
        area_yoy = round((area_y1 - area_y2) / area_y2 * 100, 1)

    prod_yoy = None
    if prod_y1 and prod_y2 and prod_y2 > 0:
        prod_yoy = round((prod_y1 - prod_y2) / prod_y2 * 100, 1)

    return {
        "area_ha_y1":          area_y1,
        "area_ha_y2":          area_y2,
        "area_ha_y3":          get(y3_year, "area_ha"),
        "production_ton_y1":   prod_y1,
        "production_ton_y2":   prod_y2,
        "production_ton_y3":   get(y3_year, "production_ton"),
        "yield_per_ha_y1":     get(y1_year, "yield_per_ha"),
        "area_yoy_change_pct": area_yoy,
        "prod_yoy_change_pct": prod_yoy,
        "kosis_latest_year":   years[0] if years else None,
    }


# ── 기상 피처 계산 ─────────────────────────────────────────────────────────

def _compute_weather_features(rows: list) -> dict:
    if not rows:
        return {}

    today = date.today()
    cutoff_7d = today - timedelta(days=7)
    recent_7d = [r for r in rows if r.date >= cutoff_7d]

    if not recent_7d:
        return {}

    temps  = [r.avg_temp for r in recent_7d if r.avg_temp is not None]
    precips = [r.precipitation for r in recent_7d if r.precipitation is not None]
    normals = [r.normal_avg_temp for r in recent_7d if r.normal_avg_temp is not None]
    alerts  = sum(
        (1 if r.heat_alert else 0) + (1 if r.cold_alert else 0) + (1 if r.heavy_rain_alert else 0)
        for r in recent_7d
    )

    avg_temp  = round(sum(temps) / len(temps), 1) if temps else None
    total_precip = round(sum(precips), 1) if precips else None

    temp_anomaly = None
    if temps and normals and len(normals) > 0:
        actual_mean = sum(temps) / len(temps)
        normal_mean = sum(normals) / len(normals)
        temp_anomaly = round(actual_mean - normal_mean, 1)

    # 기상 스트레스 지수 (0~1): 이상 기온 + 강수 + 특보 기반
    stress = 0.0
    if temp_anomaly is not None:
        stress += min(abs(temp_anomaly) / 10.0, 0.4)   # 10℃ 이상이면 최대
    if total_precip is not None and total_precip > 100:
        stress += min((total_precip - 100) / 200.0, 0.3)  # 300mm 이상이면 최대
    if alerts > 0:
        stress += min(alerts / 10.0, 0.3)
    stress = round(min(stress, 1.0), 3)

    return {
        "weather_temp_avg_7d":    avg_temp,
        "weather_precip_7d":      total_precip,
        "weather_temp_anomaly_7d": temp_anomaly,
        "weather_stress_score":   stress,
        "weather_alert_count_7d": alerts,
    }


# ── 종합 위험도 ─────────────────────────────────────────────────────────────

def _compute_risk(meta: dict) -> dict:
    factors = {}
    risk_score = 0.0

    # 가격 위험도: 전년비 ±20% 이상, MA30 대비 ±15% 이상
    price_risk = 0.0
    yoy = meta.get("yoy_change_pct")
    if yoy is not None:
        if abs(yoy) > 30:
            price_risk += 0.5
            factors["yoy_surge"] = f"전년비 {yoy:+.1f}%"
        elif abs(yoy) > 15:
            price_risk += 0.25
            factors["yoy_change"] = f"전년비 {yoy:+.1f}%"

    vs_ma30 = meta.get("price_vs_ma30_pct")
    if vs_ma30 is not None and abs(vs_ma30) > 15:
        price_risk += 0.3
        factors["price_spike"] = f"MA30 대비 {vs_ma30:+.1f}%"

    cv30 = meta.get("price_cv_30d")
    if cv30 is not None and cv30 > 0.15:
        price_risk += 0.2
        factors["high_volatility"] = f"변동계수 {cv30:.2f}"

    price_risk = round(min(price_risk, 1.0), 3)

    # 공급 위험도: 생산 감소 + 기상 스트레스
    supply_risk = 0.0
    prod_yoy = meta.get("prod_yoy_change_pct")
    if prod_yoy is not None and prod_yoy < -10:
        supply_risk += min(abs(prod_yoy) / 30.0, 0.5)
        factors["prod_decline"] = f"생산량 {prod_yoy:.1f}%"

    area_yoy = meta.get("area_yoy_change_pct")
    if area_yoy is not None and area_yoy < -5:
        supply_risk += min(abs(area_yoy) / 20.0, 0.3)
        factors["area_shrink"] = f"재배면적 {area_yoy:.1f}%"

    stress = meta.get("weather_stress_score", 0)
    if stress and stress > 0.3:
        supply_risk += stress * 0.4
        factors["weather_stress"] = f"기상스트레스 {stress:.2f}"

    supply_risk = round(min(supply_risk, 1.0), 3)

    # 종합 위험도 (가격 60%, 공급 40%)
    overall = round(price_risk * 0.6 + supply_risk * 0.4, 3)

    if overall >= 0.7:
        level = "critical"
    elif overall >= 0.45:
        level = "high"
    elif overall >= 0.2:
        level = "medium"
    else:
        level = "low"

    return {
        "price_risk_score":  price_risk,
        "supply_risk_score": supply_risk,
        "overall_risk_score": overall,
        "risk_level":        level,
        "risk_factors":      factors if factors else None,
    }


# ── DB 조회 헬퍼 ─────────────────────────────────────────────────────────────

async def _fetch_price_history(db: AsyncSession, item_code: str, days: int) -> list:
    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(DailyPrice)
        .where(DailyPrice.item_code == item_code, DailyPrice.date >= cutoff)
        .order_by(DailyPrice.date)
    )
    return result.scalars().all()


async def _fetch_production(db: AsyncSession, item_code: str) -> list:
    result = await db.execute(
        select(CropProduction)
        .where(CropProduction.item_code == item_code)
        .order_by(CropProduction.year.desc())
        .limit(5)
    )
    return result.scalars().all()


async def _fetch_weather(db: AsyncSession, item_code: str, days: int) -> list:
    region_code = ITEM_MAIN_REGION.get(item_code, {}).get("code")
    if not region_code:
        return []
    cutoff = date.today() - timedelta(days=days)
    result = await db.execute(
        select(DailyWeather)
        .where(DailyWeather.region_code == region_code, DailyWeather.date >= cutoff)
        .order_by(DailyWeather.date)
    )
    return result.scalars().all()


# ── DB upsert ────────────────────────────────────────────────────────────────

async def _upsert_meta(db: AsyncSession, item_code: str, meta: dict):
    existing = await db.get(ItemMeta, item_code)
    if existing is None:
        existing = ItemMeta(item_code=item_code)
        db.add(existing)
    for k, v in meta.items():
        if hasattr(existing, k):
            setattr(existing, k, v)
