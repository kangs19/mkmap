"""
Mock 가격 + 날씨 데이터 생성기 (5개 품목 2년치)
실제 KAMIS/KMA API 키 없이 현실적인 가격 패턴 시뮬레이션
"""
import asyncio
import sys
import os
import random
import math
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from sqlalchemy import delete
from app.database import AsyncSessionLocal, engine, Base
from app.models.price import DailyPrice
from app.models.weather import DailyWeather

# ── 품목별 가격 파라미터 ────────────────────────────────────────────
# 실제 도매가격 기반 설계 (KAMIS 참조 근사치)
ITEM_PARAMS = {
    "cabbage": {
        "base_price": 5000,      # 10kg 기준
        "volatility": 0.35,
        "seasonal": {
            1:1.30, 2:1.25, 3:1.10, 4:0.95, 5:0.90,
            6:1.00, 7:1.20, 8:1.15, 9:1.05, 10:0.85, 11:0.90, 12:1.20
        },
    },
    "radish": {
        "base_price": 12000,     # 20kg 기준
        "volatility": 0.30,
        "seasonal": {
            1:1.20, 2:1.15, 3:1.05, 4:0.90, 5:0.85,
            6:0.95, 7:1.10, 8:1.00, 9:0.90, 10:0.80, 11:0.85, 12:1.10
        },
    },
    "onion": {
        "base_price": 18000,     # 20kg 기준
        "volatility": 0.40,      # 저장성 있어 수급 충격 큼
        "seasonal": {
            1:1.30, 2:1.25, 3:1.20, 4:1.00, 5:0.75,
            6:0.70, 7:0.80, 8:0.90, 9:1.00, 10:1.10, 11:1.20, 12:1.25
        },
    },
    "green_onion": {
        "base_price": 2500,      # 1kg 기준
        "volatility": 0.50,      # 변동성 매우 높음
        "seasonal": {
            1:1.40, 2:1.35, 3:1.10, 4:0.90, 5:0.80,
            6:0.95, 7:1.20, 8:1.10, 9:1.00, 10:0.85, 11:1.00, 12:1.30
        },
    },
    "garlic": {
        "base_price": 25000,     # 10kg 기준
        "volatility": 0.25,      # 저장성 높아 상대적으로 안정
        "seasonal": {
            1:1.20, 2:1.20, 3:1.15, 4:1.10, 5:0.90,
            6:0.85, 7:0.80, 8:0.85, 9:0.90, 10:0.95, 11:1.00, 12:1.10
        },
    },
}

# 날씨 지역 설정
WEATHER_REGIONS = [
    ("KR-42", "강원"),
    ("KR-46", "전남"),
    ("KR-43", "충북"),
    ("KR-47", "경북"),
    ("KR-48", "경남"),
    ("KR-41", "경기"),
]

MONTHLY_TEMP = {
    1:-5.0, 2:-2.5, 3:4.0, 4:11.0, 5:17.0, 6:21.0,
    7:24.0, 8:24.5, 9:19.0, 10:12.0, 11:4.0, 12:-2.0
}
MONTHLY_PRECIP = {
    1:25, 2:30, 3:45, 4:60, 5:80, 6:130,
    7:280, 8:250, 9:120, 10:55, 11:40, 12:25
}
# 지역별 기온 오프셋
REGION_TEMP_OFFSET = {
    "KR-42": -3.0,  # 강원 (고랭지)
    "KR-46": +2.5,  # 전남 (남해)
    "KR-43": -1.0,  # 충북
    "KR-47": -0.5,  # 경북
    "KR-48": +1.5,  # 경남
    "KR-41": +0.5,  # 경기
}


def generate_price_series(item_code: str, start_date: date, end_date: date) -> list[dict]:
    """품목별 일별 도매가격 시뮬레이션"""
    params = ITEM_PARAMS[item_code]
    base_price = params["base_price"]
    volatility = params["volatility"]
    seasonal = params["seasonal"]

    records = []
    price = base_price
    d = start_date

    # 수급 충격 이벤트 생성
    shock_events = []
    cur = start_date
    shock_freq = {"cabbage": 0.04, "radish": 0.03, "onion": 0.05,
                  "green_onion": 0.06, "garlic": 0.02}.get(item_code, 0.04)
    while cur <= end_date:
        if random.random() < shock_freq:
            duration = random.randint(7, 28)
            magnitude = random.uniform(-0.45, 0.65)
            shock_events.append((cur, duration, magnitude))
        cur += timedelta(days=1)

    prev_seasonal = seasonal[start_date.month]
    while d <= end_date:
        curr_seasonal = seasonal[d.month]

        # 트렌드 (인플레이션 약 2~3%/년)
        days_elapsed = (d - start_date).days
        trend = 1 + 0.025 * (days_elapsed / 365)

        # 수급 충격
        shock = 0.0
        for shock_date, duration, magnitude in shock_events:
            days_in = (d - shock_date).days
            if 0 <= days_in < duration:
                shock += magnitude * math.exp(-days_in / (duration * 0.4))

        # 일별 노이즈
        noise = random.gauss(0, volatility * 0.12)

        daily_change = noise + shock * 0.07
        price = price * (1 + daily_change)

        # 계절 목표가격으로 평균 회귀
        target = base_price * curr_seasonal * trend
        price = price * 0.96 + target * 0.04

        # 가격 범위 클리핑 (품목별)
        min_p = base_price * 0.15
        max_p = base_price * 5.0
        price = max(min_p, min(max_p, price))

        prev_year_price = price * random.uniform(0.78, 1.22)
        avg_year_price = base_price * curr_seasonal * random.uniform(0.92, 1.08)

        records.append({
            "item_code": item_code,
            "date": d,
            "market": "가락시장",
            "grade": "상품",
            "wholesale_price": round(price, 0),
            "retail_price": round(price * 1.35, 0),
            "avg_year_price": round(avg_year_price, 0),
            "prev_year_price": round(prev_year_price, 0),
            "source": "mock_generator",
        })

        prev_seasonal = curr_seasonal
        d += timedelta(days=1)

    return records


def generate_weather_series(region_code: str, region_name: str,
                             start_date: date, end_date: date) -> list[dict]:
    """지역별 일별 날씨 시뮬레이션"""
    records = []
    offset = REGION_TEMP_OFFSET.get(region_code, 0.0)
    d = start_date

    while d <= end_date:
        month = d.month
        base_temp = MONTHLY_TEMP[month] + offset

        avg_temp = base_temp + random.gauss(0, 3.5)
        max_temp = avg_temp + random.uniform(3, 8)
        min_temp = avg_temp - random.uniform(3, 8)

        base_daily_precip = MONTHLY_PRECIP[month] / 30
        has_rain = random.random() < 0.35
        precipitation = random.expovariate(1 / max(base_daily_precip * 3, 0.1)) if has_rain else 0.0

        heat_alert = avg_temp > 33
        cold_alert = min_temp < -15
        heavy_rain_alert = precipitation > 80

        records.append({
            "region_code": region_code,
            "region_name": region_name,
            "date": d,
            "avg_temp": round(avg_temp, 1),
            "max_temp": round(max_temp, 1),
            "min_temp": round(min_temp, 1),
            "precipitation": round(precipitation, 1),
            "humidity": round(random.uniform(40, 90), 1),
            "wind_speed": round(max(0, random.expovariate(0.5)), 1),
            "sunshine_hours": round(max(0, random.gauss(6, 3)), 1),
            "snowfall": round(max(0, random.gauss(0, 1)) if month in [12, 1, 2] else 0, 1),
            "heat_alert": heat_alert,
            "cold_alert": cold_alert,
            "heavy_rain_alert": heavy_rain_alert,
            "normal_avg_temp": round(base_temp, 1),
            "normal_precip": round(base_daily_precip, 1),
            "source": "mock_generator",
        })
        d += timedelta(days=1)

    return records


async def main():
    print("DB 테이블 확인...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    end_date = date.today()
    start_date = date(end_date.year - 2, end_date.month, end_date.day)
    print(f"생성 기간: {start_date} ~ {end_date}")

    async with AsyncSessionLocal() as session:
        # 기존 mock 데이터 삭제
        await session.execute(delete(DailyPrice).where(DailyPrice.source == "mock_generator"))
        await session.execute(delete(DailyWeather).where(DailyWeather.source == "mock_generator"))
        await session.commit()

    async with AsyncSessionLocal() as session:
        # 날씨 데이터 (전 지역 공통, 한 번만)
        print("\n날씨 데이터 생성 중...")
        total_w = 0
        for region_code, region_name in WEATHER_REGIONS:
            wx = generate_weather_series(region_code, region_name, start_date, end_date)
            for r in wx:
                session.add(DailyWeather(**r))
            total_w += len(wx)
        await session.commit()
        print(f"  날씨 {total_w}건 ({len(WEATHER_REGIONS)}개 지역)")

    async with AsyncSessionLocal() as session:
        # 품목별 가격 데이터
        print("\n가격 데이터 생성 중...")
        for item_code in ITEM_PARAMS:
            prices = generate_price_series(item_code, start_date, end_date)
            for r in prices:
                session.add(DailyPrice(**r))
            print(f"  {item_code}: {len(prices)}건")
        await session.commit()

    print("\nMock 데이터 생성 완료!")


if __name__ == "__main__":
    asyncio.run(main())
