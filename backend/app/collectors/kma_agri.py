"""
기상청 작물별 농업주산지 상세날씨 수집기
Endpoint: https://apis.data.go.kr/1360000/FmlandWthrInfoService
같은 KMA_API_KEY 사용 — 승인 후 30~60분 후 활성화
"""
import httpx
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional
from app.config import get_settings

AGRI_BASE = "https://apis.data.go.kr/1360000/FmlandWthrInfoService"

# 작물별 농업주산지 격자 (단기예보와 동일한 nx/ny)
CROP_REGION_MAP = {
    "cabbage": [
        {"region_code": "KR-42", "region_name": "강원(고랭지)", "nx": 73, "ny": 134},
        {"region_code": "KR-43", "region_name": "충북(청주)",   "nx": 69, "ny": 107},
    ],
    "radish": [
        {"region_code": "KR-42", "region_name": "강원(강릉)",   "nx": 73, "ny": 134},
        {"region_code": "KR-48", "region_name": "경남(창원)",   "nx": 91, "ny":  77},
    ],
    "onion": [
        {"region_code": "KR-46", "region_name": "전남(무안)",   "nx": 51, "ny":  67},
        {"region_code": "KR-48", "region_name": "경남(창녕)",   "nx": 91, "ny":  77},
    ],
    "green_onion": [
        {"region_code": "KR-46", "region_name": "전남(진도)",   "nx": 51, "ny":  67},
        {"region_code": "KR-41", "region_name": "경기(이천)",   "nx": 60, "ny": 121},
    ],
    "garlic": [
        {"region_code": "KR-47", "region_name": "경북(의성)",   "nx": 89, "ny": 106},
        {"region_code": "KR-46", "region_name": "전남(고흥)",   "nx": 51, "ny":  67},
    ],
}


async def fetch_agri_village_fcst(
    nx: int,
    ny: int,
    target_date: date,
) -> Optional[dict]:
    """농업주산지 단기예보 조회"""
    settings = get_settings()
    if not settings.kma_api_key:
        return None

    base_times = ["0800", "1100", "1400", "1700", "2000", "2300", "0200", "0500"]
    now = datetime.now()
    base_time = "0800"
    for bt in base_times:
        if now.hour >= int(bt[:2]):
            base_time = bt
            break

    params = {
        "serviceKey": settings.kma_api_key,
        "pageNo": "1",
        "numOfRows": "500",
        "dataType": "JSON",
        "base_date": target_date.strftime("%Y%m%d"),
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{AGRI_BASE}/getFmlandVilageFcst", params=params)
                if r.status_code == 403:
                    return None  # 키 미활성 — 조용히 스킵
                r.raise_for_status()
                data = r.json()
            return _parse_village_fcst(data, nx, ny, target_date)
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(1)
    return None


async def fetch_agri_nowcast(
    nx: int,
    ny: int,
    target_date: date,
) -> Optional[dict]:
    """농업주산지 초단기실황"""
    settings = get_settings()
    if not settings.kma_api_key:
        return None

    now = datetime.now()
    params = {
        "serviceKey": settings.kma_api_key,
        "pageNo": "1",
        "numOfRows": "100",
        "dataType": "JSON",
        "base_date": now.strftime("%Y%m%d"),
        "base_time": f"{now.hour:02d}00",
        "nx": nx,
        "ny": ny,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{AGRI_BASE}/getFmlandVilageNcst", params=params)
            if r.status_code == 403:
                return None
            r.raise_for_status()
            data = r.json()
        return _parse_nowcast(data, nx, ny, target_date)
    except Exception:
        return None


async def fetch_crop_weather(
    item_code: str,
    target_date: date,
) -> list[dict]:
    """작물별 전체 주산지 기상 수집"""
    regions = CROP_REGION_MAP.get(item_code, [])
    results = []
    for reg in regions:
        row = await fetch_agri_village_fcst(reg["nx"], reg["ny"], target_date)
        if row:
            row["region_code"] = reg["region_code"]
            row["region_name"] = reg["region_name"]
            results.append(row)
        await asyncio.sleep(0.2)
    return results


def _parse_village_fcst(data: dict, nx: int, ny: int, target_date: date) -> Optional[dict]:
    try:
        items = data["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None

    date_str = target_date.strftime("%Y%m%d")
    vals: dict = {}

    for it in items:
        if it.get("fcstDate") != date_str:
            continue
        cat = it.get("category", "")
        try:
            v = float(it.get("fcstValue", 0))
        except (ValueError, TypeError):
            v = 0.0

        if cat == "TMP":
            vals.setdefault("temps", []).append(v)
        elif cat == "TMN":
            vals["min_temp"] = v
        elif cat == "TMX":
            vals["max_temp"] = v
        elif cat == "REH":
            vals.setdefault("humidity", []).append(v)
        elif cat == "WSD":
            vals.setdefault("wind", []).append(v)
        elif cat == "PCP":
            if v > 0:
                vals["precip"] = vals.get("precip", 0.0) + v
        elif cat == "SNO":
            if v > 0:
                vals["snow"] = vals.get("snow", 0.0) + v
        elif cat == "SKY":
            vals.setdefault("sky", []).append(v)

    if not vals.get("temps"):
        return None

    temps = vals["temps"]
    avg_temp = sum(temps) / len(temps)
    min_temp = vals.get("min_temp", min(temps))
    max_temp = vals.get("max_temp", max(temps))
    precip = vals.get("precip", 0.0)
    snow = vals.get("snow", 0.0)
    humidity = sum(vals.get("humidity", [60])) / max(len(vals.get("humidity", [1])), 1)
    wind = sum(vals.get("wind", [2])) / max(len(vals.get("wind", [1])), 1)
    sky = sum(vals.get("sky", [1])) / max(len(vals.get("sky", [1])), 1)

    return {
        "date": target_date,
        "avg_temp": round(avg_temp, 1),
        "max_temp": round(max_temp, 1),
        "min_temp": round(min_temp, 1),
        "precipitation": round(precip, 1),
        "humidity": round(humidity, 1),
        "wind_speed": round(wind, 1),
        "sunshine_hours": round(max(0, 10 - sky * 2.5), 1),
        "snowfall": round(snow, 1),
        "heat_alert": max_temp > 33,
        "cold_alert": min_temp < -15,
        "heavy_rain_alert": precip > 80,
        "normal_avg_temp": avg_temp,
        "normal_precip": precip / 30,
        "source": "kma_agri",
    }


def _parse_nowcast(data: dict, nx: int, ny: int, target_date: date) -> Optional[dict]:
    try:
        items = data["response"]["body"]["items"]["item"]
    except (KeyError, TypeError):
        return None

    vals = {}
    for it in items:
        cat = it.get("category", "")
        try:
            v = float(it.get("obsrValue", 0))
        except (ValueError, TypeError):
            v = 0.0
        vals[cat] = v

    temp = vals.get("T1H", 0.0)
    precip = vals.get("RN1", 0.0)
    humidity = vals.get("REH", 60.0)
    wind = vals.get("WSD", 2.0)

    return {
        "date": target_date,
        "avg_temp": round(temp, 1),
        "max_temp": round(temp + 3, 1),
        "min_temp": round(temp - 3, 1),
        "precipitation": round(precip, 1),
        "humidity": round(humidity, 1),
        "wind_speed": round(wind, 1),
        "sunshine_hours": 6.0,
        "snowfall": 0.0,
        "heat_alert": temp > 33,
        "cold_alert": temp < -15,
        "heavy_rain_alert": precip > 80,
        "normal_avg_temp": temp,
        "normal_precip": 0.0,
        "source": "kma_agri",
    }
