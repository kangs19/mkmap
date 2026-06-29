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
from app.models.production import CropProduction


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
                   production_stats: dict = None) -> pd.DataFrame:
    """가격 + 날씨 피처 조합 → 모델 입력 DataFrame"""
    df = price_df.copy()

    # ── 가격 피처 ──────────────────────────────────────────────
    df["price_ma7"] = df["price"].rolling(7).mean()
    df["price_ma14"] = df["price"].rolling(14).mean()
    df["price_ma28"] = df["price"].rolling(28).mean()

    df["ret_1d"] = df["price"].pct_change(1)
    df["ret_7d"] = df["price"].pct_change(7)
    df["ret_14d"] = df["price"].pct_change(14)

    df["volatility_7d"] = df["ret_1d"].rolling(7).std()
    df["volatility_14d"] = df["ret_1d"].rolling(14).std()

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

        df["w_temp_ma7"] = df["w_avg_temp"].rolling(7).mean()
        df["w_precip_ma7"] = df["w_precipitation"].rolling(7).sum()
        df["w_heat_alert_7d"] = df["w_heat_alert"].rolling(7).sum()
        df["w_cold_alert_7d"] = df["w_cold_alert"].rolling(7).sum()
        df["w_heavy_rain_7d"] = df["w_heavy_rain_alert"].rolling(7).sum()
    else:
        for col in ["w_avg_temp", "w_precipitation", "w_temp_dev",
                    "w_temp_ma7", "w_precip_ma7",
                    "w_heat_alert_7d", "w_cold_alert_7d", "w_heavy_rain_7d"]:
            df[col] = 0.0

    # ── KOSIS 생산통계 피처 (연간 → 전체 기간에 상수로 적용) ──
    if production_stats and production_stats.get("has_kosis"):
        df["kosis_area_dev"] = production_stats["area_dev"]      # 재배면적 전년비 편차
        df["kosis_prod_dev"] = production_stats["prod_dev"]      # 생산량 전년비 편차
        df["kosis_supply_risk"] = -production_stats["prod_dev"]  # 생산↓ → 공급위험↑
    else:
        df["kosis_area_dev"] = 0.0
        df["kosis_prod_dev"] = 0.0
        df["kosis_supply_risk"] = 0.0

    # ── 타겟 ──────────────────────────────────────────────────
    # 14일 후 가격 방향 (1=상승, 0=하락/보합)
    future_price = df["price"].shift(-14)
    df["target_direction"] = (future_price > df["price"] * 1.03).astype(int)
    # 14일 내 급등 (15% 이상 상승)
    future_max = df["price"].rolling(14, min_periods=1).max().shift(-14)
    df["target_surge"] = (future_max > df["price"] * 1.15).astype(int)

    df = df.dropna(subset=["price_ma28", "ret_14d", "target_direction"])
    return df


FEATURE_COLS = [
    "price_ma7", "price_ma14", "price_ma28",
    "ret_1d", "ret_7d", "ret_14d",
    "volatility_7d", "volatility_14d",
    "price_vs_avg_year", "price_vs_prev_year",
    "ma7_vs_ma28",
    "sin_month", "cos_month",
    "w_avg_temp", "w_precipitation", "w_temp_dev",
    "w_temp_ma7", "w_precip_ma7",
    "w_heat_alert_7d", "w_cold_alert_7d", "w_heavy_rain_7d",
    "kosis_area_dev", "kosis_prod_dev", "kosis_supply_risk",
]
