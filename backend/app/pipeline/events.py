"""
달력 이벤트 엔진 — 기획서 11번

품목별 수요 이벤트(김장철, 추석, 설, 개학 등)까지의 거리를 계산해
LightGBM 피처로 변환한다.

주요 피처:
  days_to_kimjang   — 김장철(11/15 기준) 까지 남은 일수 (음수=지남)
  is_kimjang_season — 10/15 ~ 12/15 구간 여부
  days_to_chuseok   — 당해 추석까지 남은 일수
  days_to_seol      — 당해 설까지 남은 일수
  is_school_demand  — 급식 수요기 (3월, 9월)
  is_summer_break   — 급식 중단기 (7/15 ~ 8/31)
"""

from datetime import date, timedelta
import pandas as pd
import numpy as np

# ── 추석/설 음력→양력 변환 테이블 (2020~2030)
# 실제 한국천문연구원 기준
CHUSEOK = {
    2020: date(2020, 10,  1),
    2021: date(2021,  9, 21),
    2022: date(2022,  9, 10),
    2023: date(2023,  9, 29),
    2024: date(2024,  9, 17),
    2025: date(2025, 10,  6),
    2026: date(2026,  9, 25),
    2027: date(2027,  9, 15),
    2028: date(2028, 10,  3),
    2029: date(2029,  9, 22),
    2030: date(2030,  9, 12),
}

SEOL = {
    2020: date(2020,  1, 25),
    2021: date(2021,  2, 12),
    2022: date(2022,  2,  1),
    2023: date(2023,  1, 22),
    2024: date(2024,  2, 10),
    2025: date(2025,  1, 29),
    2026: date(2026,  2, 17),
    2027: date(2027,  2,  6),
    2028: date(2028,  1, 26),
    2029: date(2029,  2, 13),
    2030: date(2030,  2,  3),
}

# 김장철 피크일 (11월 15일 고정)
KIMJANG_PEAK_MONTH = 11
KIMJANG_PEAK_DAY   = 15
KIMJANG_START_MONTH, KIMJANG_START_DAY = 10, 15
KIMJANG_END_MONTH,   KIMJANG_END_DAY   = 12, 15


def _kimjang_peak(year: int) -> date:
    return date(year, KIMJANG_PEAK_MONTH, KIMJANG_PEAK_DAY)


def _kimjang_window(target_date: date) -> bool:
    y = target_date.year
    start = date(y, KIMJANG_START_MONTH, KIMJANG_START_DAY)
    end   = date(y, KIMJANG_END_MONTH,   KIMJANG_END_DAY)
    return start <= target_date <= end


def _nearest_event(target_date: date, table: dict) -> int:
    """table 에서 target_date 에 가장 가까운 이벤트까지의 일수 반환 (음수=지남)"""
    year = target_date.year
    candidates = []
    for y in [year - 1, year, year + 1]:
        ev = table.get(y)
        if ev:
            candidates.append((ev - target_date).days)
    if not candidates:
        return 0
    # 절댓값 가장 작은 것
    return min(candidates, key=abs)


def _days_to_kimjang(target_date: date) -> int:
    """김장철 피크까지 남은 일수 (음수=지남)"""
    y = target_date.year
    peak = _kimjang_peak(y)
    diff = (peak - target_date).days
    # 작년·내년 중 더 가까운 것 선택
    for adj in [-1, 1]:
        p2 = _kimjang_peak(y + adj)
        d2 = (p2 - target_date).days
        if abs(d2) < abs(diff):
            diff = d2
    return diff


def _is_school_demand(target_date: date) -> int:
    """3월·9월 = 급식 수요 증가 (1), 그 외 0"""
    return int(target_date.month in (3, 9))


def _is_summer_break(target_date: date) -> int:
    """7/15 ~ 8/31 = 급식 중단, 학교 수요 급감 (1)"""
    y = target_date.year
    return int(date(y, 7, 15) <= target_date <= date(y, 8, 31))


def compute_event_features(target_date: date) -> dict:
    """단일 날짜의 이벤트 피처 딕셔너리 반환"""
    days_kimjang  = _days_to_kimjang(target_date)
    days_chuseok  = _nearest_event(target_date, CHUSEOK)
    days_seol     = _nearest_event(target_date, SEOL)

    return {
        "days_to_kimjang":    days_kimjang,
        "is_kimjang_season":  int(_kimjang_window(target_date)),
        # 30일 이내 접근 시 신호 강화 (비선형 효과 근사)
        "kimjang_proximity":  max(0.0, 1.0 - abs(days_kimjang) / 30) if abs(days_kimjang) <= 30 else 0.0,
        "days_to_chuseok":    days_chuseok,
        "chuseok_proximity":  max(0.0, 1.0 - abs(days_chuseok) / 14) if abs(days_chuseok) <= 14 else 0.0,
        "days_to_seol":       days_seol,
        "seol_proximity":     max(0.0, 1.0 - abs(days_seol) / 14) if abs(days_seol) <= 14 else 0.0,
        "is_school_demand":   _is_school_demand(target_date),
        "is_summer_break":    _is_summer_break(target_date),
    }


def add_event_features(df: pd.DataFrame) -> pd.DataFrame:
    """DatetimeIndex를 가진 DataFrame에 이벤트 피처 컬럼 추가"""
    records = []
    for ts in df.index:
        d = ts.date() if hasattr(ts, "date") else ts
        records.append(compute_event_features(d))

    ev_df = pd.DataFrame(records, index=df.index)
    return df.join(ev_df, how="left")


EVENT_FEATURE_COLS = [
    "days_to_kimjang",
    "is_kimjang_season",
    "kimjang_proximity",
    "days_to_chuseok",
    "chuseok_proximity",
    "days_to_seol",
    "seol_proximity",
    "is_school_demand",
    "is_summer_break",
]
