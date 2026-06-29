"""
Feature engineering: DB에서 가격/날씨 데이터를 읽어 LightGBM 입력 피처 DataFrame 생성
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price import DailyPrice
from app.models.weather import DailyWeather
from app.models.market import DailyMarket
from app.models.production import CropProduction
from app.pipeline.events import add_event_features, EVENT_FEATURE_COLS


async def load_price_df(db: AsyncSession, item_code: str,
                        start_date: date, end_date: date) -> pd.DataFrame:
    result = await db.execute(
        select(DailyPrice).where(
            and_(
                DailyPrice.item_code == item_code,
                DailyPrice.date >= start_date,
                DailyPrice.date <= end_date,
            )
        ).order_by(DailyPrice.date)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": r.date,
        "price": r.wholesale_price,
        "avg_year_price": r.avg_year_price,
        "prev_year_price": r.prev_year_price,
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


async def load_production_stats(db: AsyncSession, item_code: str, base_year: int) -> dict:
    """KOSIS 재배면적·생산량: 최근 3년 평균 대비 당해 편차 반환"""
    result = await db.execute(
        select(CropProduction)
        .where(
            CropProduction.item_code == item_code,
            CropProduction.year >= base_year - 3,
            CropProduction.year <= base_year,
        )
        .order_by(CropProduction.year)
    )
    rows = result.scalars().all()

    if not rows:
        return {"area_dev": 0.0, "prod_dev": 0.0, "has_kosis": False}

    latest = max(rows, key=lambda r: r.year)
    hist = [r for r in rows if r.year < latest.year]

    avg_area = sum(r.area_ha for r in hist if r.area_ha) / max(len([r for r in hist if r.area_ha]), 1)
    avg_prod = sum(r.production_ton for r in hist if r.production_ton) / max(len([r for r in hist if r.production_ton]), 1)

    area_dev = ((latest.area_ha or avg_area) - avg_area) / max(avg_area, 1) if avg_area else 0.0
    prod_dev = ((latest.production_ton or avg_prod) - avg_prod) / max(avg_prod, 1) if avg_prod else 0.0

    return {
        "area_dev": round(area_dev, 4),
        "prod_dev": round(prod_dev, 4),
        "area_ha": latest.area_ha,
        "production_ton": latest.production_ton,
        "has_kosis": True,
    }


async def load_market_df(db: AsyncSession, item_code: str,
                         start_date: date, end_date: date) -> pd.DataFrame:
    """거래량 데이터 로드 (daily_market 테이블)"""
    result = await db.execute(
        select(DailyMarket).where(
            and_(
                DailyMarket.item_code == item_code,
                DailyMarket.date >= start_date,
                DailyMarket.date <= end_date,
            )
        ).order_by(DailyMarket.date)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": r.date,
        "volume_kg": r.volume_kg,
        "trade_amount": r.trade_amount,
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


async def load_weather_df(db: AsyncSession, region_code: str,
                          start_date: date, end_date: date) -> pd.DataFrame:
    result = await db.execute(
        select(DailyWeather).where(
            and_(
                DailyWeather.region_code == region_code,
                DailyWeather.date >= start_date,
                DailyWeather.date <= end_date,
            )
        ).order_by(DailyWeather.date)
    )
    rows = result.scalars().all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": r.date,
        "avg_temp": r.avg_temp,
        "precipitation": r.precipitation,
        "heat_alert": int(r.heat_alert),
        "cold_alert": int(r.cold_alert),
        "heavy_rain_alert": int(r.heavy_rain_alert),
        "temp_dev": (r.avg_temp or 0) - (r.normal_avg_temp or 0),
    } for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def build_features(price_df: pd.DataFrame, weather_df: pd.DataFrame,
                   production_stats: dict = None,
                   market_df: pd.DataFrame = None) -> pd.DataFrame:
    """가격 + 날씨 피처 조합 → 모델 입력 DataFrame"""
    df = price_df.copy()

    # ── 가격 피처 ──────────────────────────────────────────────
    # min_periods=1 로 초기 데이터 부족 시에도 NaN 없이 근사값 생성
    df["price_ma7"]  = df["price"].rolling(7,  min_periods=1).mean()
    df["price_ma14"] = df["price"].rolling(14, min_periods=1).mean()
    df["price_ma28"] = df["price"].rolling(28, min_periods=1).mean()

    df["ret_1d"]  = df["price"].pct_change(1).fillna(0)
    df["ret_7d"]  = df["price"].pct_change(7).fillna(0)
    df["ret_14d"] = df["price"].pct_change(14).fillna(0)

    df["volatility_7d"]  = df["ret_1d"].rolling(7,  min_periods=1).std().fillna(0)
    df["volatility_14d"] = df["ret_1d"].rolling(14, min_periods=1).std().fillna(0)

    # 평년 대비 편차
    df["price_vs_avg_year"] = (df["price"] / df["avg_year_price"].replace(0, np.nan)) - 1
    df["price_vs_prev_year"] = (df["price"] / df["prev_year_price"].replace(0, np.nan)) - 1

    # 이동평균 크로스오버
    df["ma7_vs_ma28"] = (df["price_ma7"] / df["price_ma28"].replace(0, np.nan)) - 1

    # 급등 여부 (과거 7일 대비 10% 이상)
    df["surge_7d"] = (df["ret_7d"] > 0.10).astype(int)

    # 계절성
    df["month"] = df.index.month
    df["day_of_year"] = df.index.dayofyear
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12)

    # ── 날씨 피처 ──────────────────────────────────────────────
    if not weather_df.empty:
        w = weather_df.add_prefix("w_")
        df = df.join(w, how="left")

        df["w_temp_ma7"]      = df["w_avg_temp"].rolling(7, min_periods=1).mean()
        df["w_precip_ma7"]    = df["w_precipitation"].rolling(7, min_periods=1).sum()
        df["w_heat_alert_7d"] = df["w_heat_alert"].rolling(7, min_periods=1).sum()
        df["w_cold_alert_7d"] = df["w_cold_alert"].rolling(7, min_periods=1).sum()
        df["w_heavy_rain_7d"] = df["w_heavy_rain_alert"].rolling(7, min_periods=1).sum()
    else:
        for col in ["w_avg_temp", "w_precipitation", "w_temp_dev",
                    "w_temp_ma7", "w_precip_ma7",
                    "w_heat_alert_7d", "w_cold_alert_7d", "w_heavy_rain_7d"]:
            df[col] = 0.0

    # ── KOSIS 생산통계 피처 (연간 → 전체 기간에 상수로 적용) ──
    if production_stats and production_stats.get("has_kosis"):
        df["kosis_area_dev"] = production_stats["area_dev"]
        df["kosis_prod_dev"] = production_stats["prod_dev"]
        df["kosis_supply_risk"] = -production_stats["prod_dev"]
    else:
        df["kosis_area_dev"] = 0.0
        df["kosis_prod_dev"] = 0.0
        df["kosis_supply_risk"] = 0.0

    # ── 거래량 피처 ────────────────────────────────────────────
    if market_df is not None and not market_df.empty:
        m = market_df.add_prefix("mkt_")
        df = df.join(m, how="left")
        df["mkt_volume_kg"] = df["mkt_volume_kg"].ffill().fillna(0)
        df["mkt_volume_ma7"]  = df["mkt_volume_kg"].rolling(7,  min_periods=1).mean()
        df["mkt_volume_ma28"] = df["mkt_volume_kg"].rolling(28, min_periods=1).mean()
        # 평균 대비 거래량 편차 (공급 과잉/부족 신호)
        df["mkt_volume_vs_avg"] = (df["mkt_volume_kg"] / df["mkt_volume_ma28"].replace(0, np.nan)) - 1
        df["mkt_volume_trend"]  = df["mkt_volume_kg"].pct_change(7)
    else:
        for col in ["mkt_volume_kg", "mkt_volume_ma7", "mkt_volume_ma28",
                    "mkt_volume_vs_avg", "mkt_volume_trend"]:
            df[col] = 0.0

    # ── 수요 이벤트 피처 (김장철, 추석, 설, 개학) ──────────────
    df = add_event_features(df)

    # ── 타겟 ──────────────────────────────────────────────────
    # 14일 후 가격 방향 (1=상승, 0=하락/보합)
    future_price = df["price"].shift(-14)
    df["target_direction"] = (future_price > df["price"] * 1.03).astype(int)
    # 14일 내 급등 (15% 이상 상승)
    future_max = df["price"].rolling(14, min_periods=1).max().shift(-14)
    df["target_surge"] = (future_max > df["price"] * 1.15).astype(int)

    # target_direction 이 NaN인 마지막 14행만 제거 (미래 데이터 없는 구간)
    df = df.dropna(subset=["target_direction"])
    return df


FEATURE_COLS = [
    # 가격 피처 (13)
    "price_ma7", "price_ma14", "price_ma28",
    "ret_1d", "ret_7d", "ret_14d",
    "volatility_7d", "volatility_14d",
    "price_vs_avg_year", "price_vs_prev_year",
    "ma7_vs_ma28",
    "sin_month", "cos_month",
    # 날씨 피처 (8)
    "w_avg_temp", "w_precipitation", "w_temp_dev",
    "w_temp_ma7", "w_precip_ma7",
    "w_heat_alert_7d", "w_cold_alert_7d", "w_heavy_rain_7d",
    # KOSIS 생산통계 피처 (3)
    "kosis_area_dev", "kosis_prod_dev", "kosis_supply_risk",
    # 거래량 피처 (5)
    "mkt_volume_kg", "mkt_volume_ma7", "mkt_volume_ma28",
    "mkt_volume_vs_avg", "mkt_volume_trend",
    # 수요 이벤트 피처 (9)
    "days_to_kimjang", "is_kimjang_season", "kimjang_proximity",
    "days_to_chuseok", "chuseok_proximity",
    "days_to_seol", "seol_proximity",
    "is_school_demand", "is_summer_break",
]
