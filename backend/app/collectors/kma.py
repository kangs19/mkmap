"""
KMA 기상청 단기예보 수집기
API: https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0
"""
import httpx
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional
from app.config import get_settings

KMA_BASE = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

# 주산지별 격자 좌표 (기상청 단기예보 격자)
# nx, ny: 기상청 격자 좌표
REGION_GRID = {
    "KR-42": {"nx": 73, "ny": 134, "name": "강원(강릉)"},   # 강원 강릉
    "KR-46": {"nx": 51, "ny":  67, "name": "전남(무안)"},   # 전남 무안
    "KR-43": {"nx": 69, "ny": 107, "name": "충북(청주)"},   # 충북 청주
    "KR-47": {"nx": 89, "ny": 106, "name": "경북(의성)"},   # 경북 의성
    "KR-48": {"nx": 91, "ny":  77, "name": "경남(창원)"},   # 경남 창원
    "KR-41": {"nx": 60, "ny": 121, "name": "경기(수원)"},   # 경기 수원
}

# 단기예보 카테고리
TMP  = "TMP"   # 기온 (°C)
TMN  = "TMN"   # 최저기온
TMX  = "TMX"   # 최고기온
PCP  = "PCP"   # 1시간 강수량
REH  = "REH"   # 습도 (%)
WSD  = "WSD"   # 풍속 (m/s)
SKY  = "SKY"   # 하늘상태 (1맑음 3구름 4흐림)
PTY  = "PTY"   # 강수형태 (0없음 1비 2비/눈 3눈 4소나기)


async def fetch_forecast(
    region_code: str,
    base_date: date,
) -> Optional[dict]:
    """단기예보 조회 → 일별 기상 요약 반환"""
    settings = get_settings()
    if not settings.kma_api_key:
        return None

    grid = REGION_GRID.get(region_code)
    if not grid:
        return None

    # 기상청 단기예보는 하루 4회 발표: 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300
    # 가장 최근 발표시각 사용
    now = datetime.now()
    base_times = ["2300", "2000", "1700", "1400", "1100", "0800", "0500", "0200"]
    base_time = "0800"  # 기본값
    for bt in base_times:
        hour = int(bt[:2])
        if now.hour >= hour:
            base_time = bt
            break

    date_str = base_date.strftime("%Y%m%d")

    params = {
        "serviceKey": settings.kma_api_key,
        "pageNo": "1",
        "numOfRows": "1000",
        "dataType": "JSON",
        "base_date": date_str,
        "base_time": base_time,
        "nx": grid["nx"],
        "ny": grid["ny"],
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"{KMA_BASE}/getVilageFcst",
                    params=params,
                )
                r.raise_for_status()
                data = r.json()
            return _parse_forecast(data, region_code, grid["name"], base_date)
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(1)

    return None


async def fetch_ultra_short(
    region_code: str,
    base_date: date,
) -> Optional[dict]:
    """초단기실황 조회 → 오늘 실시간 기상"""
    settings = get_settings()
    if not settings.kma_api_key:
        return None

    grid = REGION_GRID.get(region_code)
    if not grid:
        return None

    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    # 매 정시 발표
    time_str = f"{(now.hour):02d}00"

    params = {
        "serviceKey": settings.kma_api_key,
        "pageNo": "1",
        "numOfRows": "100",
        "dataType": "JSON",
        "base_date": date_str,
        "base_time": time_str,
        "nx": grid["nx"],
        "ny": grid["ny"],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{KMA_BASE}/getUltraSrtNcst",
                params=params,
            )
            r.raise_for_status()
            data = r.json()
        return _parse_ultra(data, region_code, grid["name"], base_date)
    except Exception:
        return None


def _parse_forecast(data: dict, region_code: str, region_name: str, base_date: date) -> Optional[dict]:
    try:
        items = data["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None

    date_str = base_date.strftime("%Y%m%d")
    vals = {}
    for it in items:
        if it.get("fcstDate") != date_str:
            continue
        cat = it.get("category")
        try:
            v = float(it.get("fcstValue", 0))
        except (ValueError, TypeError):
            v = 0.0
        # 하루 중 대표값 취합
        if cat == TMP:
            vals.setdefault("temps", []).append(v)
        elif cat == TMN:
            vals["min_temp"] = v
        elif cat == TMX:
            vals["max_temp"] = v
        elif cat == REH:
            vals.setdefault("humidity", []).append(v)
        elif cat == WSD:
            vals.setdefault("wind", []).append(v)
        elif cat == PCP:
            if v > 0:
                vals["precip"] = vals.get("precip", 0) + v
        elif cat == SKY:
            vals.setdefault("sky", []).append(v)

    if not vals.get("temps"):
        return None

    avg_temp = sum(vals["temps"]) / len(vals["temps"])
    min_temp = vals.get("min_temp", min(vals["temps"]))
    max_temp = vals.get("max_temp", max(vals["temps"]))
    precipitation = vals.get("precip", 0.0)
    humidity = sum(vals.get("humidity", [60])) / max(len(vals.get("humidity", [1])), 1)
    wind_speed = sum(vals.get("wind", [2])) / max(len(vals.get("wind", [1])), 1)
    sky_avg = sum(vals.get("sky", [1])) / max(len(vals.get("sky", [1])), 1)
    sunshine_hours = max(0, 10 - sky_avg * 2.5)

    return {
        "region_code": region_code,
        "region_name": region_name,
        "date": base_date,
        "avg_temp": round(avg_temp, 1),
        "max_temp": round(max_temp, 1),
        "min_temp": round(min_temp, 1),
        "precipitation": round(precipitation, 1),
        "humidity": round(humidity, 1),
        "wind_speed": round(wind_speed, 1),
        "sunshine_hours": round(sunshine_hours, 1),
        "snowfall": 0.0,
        "heat_alert": max_temp > 33,
        "cold_alert": min_temp < -15,
        "heavy_rain_alert": precipitation > 80,
        "normal_avg_temp": avg_temp,
        "normal_precip": precipitation / 30,
        "source": "kma_forecast",
    }


def _parse_ultra(data: dict, region_code: str, region_name: str, base_date: date) -> Optional[dict]:
    try:
        items = data["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None

    vals = {}
    for it in items:
        cat = it.get("category")
        try:
            v = float(it.get("obsrValue", 0))
        except (ValueError, TypeError):
            v = 0.0
        vals[cat] = v

    temp = vals.get("T1H", 0)
    precipitation = vals.get("RN1", 0)
    humidity = vals.get("REH", 60)
    wind_speed = vals.get("WSD", 2)

    return {
        "region_code": region_code,
        "region_name": region_name,
        "date": base_date,
        "avg_temp": round(temp, 1),
        "max_temp": round(temp + 3, 1),
        "min_temp": round(temp - 3, 1),
        "precipitation": round(precipitation, 1),
        "humidity": round(humidity, 1),
        "wind_speed": round(wind_speed, 1),
        "sunshine_hours": 6.0,
        "snowfall": 0.0,
        "heat_alert": temp > 33,
        "cold_alert": temp < -15,
        "heavy_rain_alert": precipitation > 80,
        "normal_avg_temp": temp,
        "normal_precip": 0.0,
        "source": "kma_ultra",
    }
