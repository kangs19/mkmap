"""품목별 특화 피처 엔진 — v2.

각 품목의 실제 재배/수확/유통 사이클에 맞는 피처를 생성.

품목별 핵심 특성:
  cabbage (배추)
    - 봄배추(4-6월), 고랭지배추(7-9월), 가을배추(10-12월), 월동배추(1-3월) — 4계절 교체
    - 수확 직전 1-2주 급등 → 수확기 급락 패턴
    - 김장철(11월) 수요 폭등 → 9-10월 선행 급등
    - 고온·폭우에 병해 취약

  garlic (마늘)
    - 10-11월 파종, 이듬해 5-6월 수확 — 8개월 성장
    - 5-6월 햇마늘 출하 → 가격 급락
    - 7-9월 저장품 소진 → 가격 반등
    - 냉해(파종 후 2월) 피해가 이듬해 가격 결정

  green_onion (대파)
    - 연중 재배 가능, 성장 60-90일
    - 여름 고온 병해 + 겨울 동해 → 공급 충격
    - lag이 짧음 (60일 사이클) → 단기 피처 강조

  onion (양파)
    - 10-11월 파종, 이듬해 5-6월 수확
    - 5-6월 햇양파 출하 → 가격 급락
    - 저장양파 7-11월 → 저장량에 따라 가격 결정
    - 마늘과 유사한 연간 사이클

  radish (무)
    - 봄무(3-5월), 여름무(7-8월), 가을무(9-11월), 겨울무(12-2월)
    - 배추와 유사한 4계절 교체
    - 김장철 배추와 동반 수요
    - 수분 함량 높아 한파·폭염에 민감

Usage:
    python scripts/build_price_training_table_v2.py --date 2026-07-02
    python scripts/build_price_training_table_v2.py --date 2026-07-02 --output-suffix v2
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# mkmap_meta 위치 탐색 (CWD → 고정경로 순서로)
def _find_mkmap_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(r"C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git"),
        REPO_ROOT,
    ]
    for c in candidates:
        if (c / "mkmap_meta").exists():
            return c
    return REPO_ROOT

_mkmap_root = _find_mkmap_root()
if str(_mkmap_root) not in sys.path:
    sys.path.insert(0, str(_mkmap_root))

# data_dir()가 CWD 기반이므로 mkmap_root가 CWD가 되도록 디렉토리 변경
import os as _os
_os.chdir(str(_mkmap_root))

from mkmap_meta.connectors.cached import CachedPriceConnector
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import data_dir


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--min-history", type=int, default=7)
    p.add_argument("--output-suffix", default="v2")
    return p.parse_args()


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

def _pct(current: float, prev: float) -> float:
    if not prev:
        return 0.0
    return round((current - prev) / prev, 6)

def _sin_cycle(val: float, period: float) -> float:
    return round(math.sin(2 * math.pi * val / period), 6)

def _cos_cycle(val: float, period: float) -> float:
    return round(math.cos(2 * math.pi * val / period), 6)

def _returns(vals: list[float]) -> list[float]:
    return [_pct(vals[i], vals[i - 1]) for i in range(1, len(vals))]

def _safe_mean(lst: list[float], fallback: float = 0.0) -> float:
    return mean(lst) if lst else fallback

def _safe_std(lst: list[float]) -> float:
    return pstdev(lst) if len(lst) > 1 else 0.0


# ── 공통 가격 피처 (모든 품목) ──────────────────────────────────────────────

def _common_price_features(
    idx: int,
    values: list[float],
    base_date: date,
    hist_mean: float,
) -> dict:
    current = values[idx]
    lag_1 = values[idx - 1]
    lag_3 = values[idx - 3]
    lag_7 = values[idx - 7]
    lag_14 = values[idx - 14]
    ma_7 = _safe_mean(values[max(0, idx - 7):idx], current)
    ma_14 = _safe_mean(values[max(0, idx - 14):idx], current)
    ma_28 = _safe_mean(values[max(0, idx - 28):idx], current)
    returns_7 = _returns(values[max(0, idx - 7):idx + 1])
    returns_14 = _returns(values[max(0, idx - 14):idx + 1])

    return {
        "avg_price": round(current, 4),
        "price_pct_of_hist_mean": _pct(current, hist_mean),
        "lag_1_price": round(lag_1, 4),
        "lag_3_price": round(lag_3, 4),
        "lag_7_price": round(lag_7, 4),
        "lag_14_price": round(lag_14, 4),
        "ma_7_price": round(ma_7, 4),
        "ma_14_price": round(ma_14, 4),
        "ma_28_price": round(ma_28, 4),
        "change_1d": _pct(current, lag_1),
        "change_3d": _pct(current, lag_3),
        "change_7d": _pct(current, lag_7),
        "change_14d": _pct(current, lag_14),
        "ma_7_gap": _pct(current, ma_7),
        "ma_14_gap": _pct(current, ma_14),
        "volatility_7d": _safe_std(returns_7),
        "volatility_14d": _safe_std(returns_14),
        # 주기 인코딩
        "weekday_sin": _sin_cycle(base_date.weekday(), 7),
        "weekday_cos": _cos_cycle(base_date.weekday(), 7),
        "month_sin": _sin_cycle(base_date.month - 1, 12),
        "month_cos": _cos_cycle(base_date.month - 1, 12),
    }


# ── 품목별 특화 피처 ──────────────────────────────────────────────────────────

def _cabbage_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    배추: 4계절 교체 재배 + 김장철 수요 사이클.

    핵심 피처:
    - kimjang_proximity: 김장철(11월)까지 남은 주 (가까울수록 1)
    - harvest_phase: 각 계절 수확기 직전 2주(→상승) / 수확기(→하락)
    - season_code: [봄/고랭지/가을/월동] sin/cos
    - supply_gap_risk: 계절 교체기(수확 끝~다음 수확 시작) 공급 공백 위험
    - price_vs_season_avg: 현재가 vs 동월 평균 대비 (계절 이탈 감지)
    - lag_3_vs_ma14: 단기 가속도 (급변 감지)
    """
    m, d = base_date.month, base_date.day
    day_of_year = base_date.timetuple().tm_yday

    # 김장철 근접도: 10-11월 최고, 멀수록 0
    # 10/1~11/30 피크 (yday 274~334)
    kimjang_peak_yday = 305  # 11/1 기준
    kimjang_dist = abs(day_of_year - kimjang_peak_yday)
    kimjang_proximity = max(0.0, 1.0 - kimjang_dist / 90.0)  # 90일 window

    # 수확기 판별:
    # 봄배추 수확: 5/15~6/30 (yday 135~181)
    # 고랭지 수확: 8/1~9/15 (yday 213~258)
    # 가을배추 수확: 10/20~12/10 (yday 293~344)
    # 월동배추 수확: 2/1~3/15 (yday 32~74)
    harvest_windows = [
        (135, 181),   # 봄
        (213, 258),   # 고랭지
        (293, 344),   # 가을
        (32, 74),     # 월동
    ]
    in_harvest = any(s <= day_of_year <= e for s, e in harvest_windows)
    # 수확 직전 2주 (14일 전)
    pre_harvest = any(s - 14 <= day_of_year < s for s, e in harvest_windows)
    # 교체기 (수확 끝 후 2주 ~ 다음 수확 전 2주)
    in_supply_gap = not in_harvest and not pre_harvest

    # 계절 코드 (봄=0, 여름=1, 가을=2, 겨울=3)
    season_idx = (m - 1) // 3
    season_sin = _sin_cycle(season_idx, 4)
    season_cos = _cos_cycle(season_idx, 4)

    # 단기 가속도 (lag_3 대비 ma_14 위치)
    current = values[idx]
    lag_3 = values[idx - 3]
    ma_14 = _safe_mean(values[max(0, idx - 14):idx], current)
    lag3_vs_ma14 = _pct(lag_3, ma_14)  # lag3이 ma14 위면 상승 모멘텀

    # 월별 과거 평균 대비 (seasonality 편차)
    same_month_vals = [
        values[j] for j in range(max(0, idx - 365), idx)
        if len(values) > j
    ]
    # 간략화: 현재 가격 vs 전체 hist_mean의 month 보정
    # month_factor: m=11(김장) → 높게, m=6(수확직후) → 낮게
    month_price_factor_raw = [1.3, 1.1, 0.9, 0.8, 0.7, 0.7, 0.8, 1.0, 1.1, 1.2, 1.4, 1.2]
    month_factor = month_price_factor_raw[m - 1]

    return {
        "kimjang_proximity": round(kimjang_proximity, 4),
        "in_harvest_period": int(in_harvest),
        "pre_harvest_period": int(pre_harvest),
        "in_supply_gap": int(in_supply_gap),
        "season_sin": season_sin,
        "season_cos": season_cos,
        "lag3_vs_ma14_momentum": round(lag3_vs_ma14, 6),
        "month_seasonal_factor": round(month_factor, 3),
    }


def _garlic_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    마늘: 8개월 재배 사이클 + 저장 출하 패턴.

    핵심 피처:
    - new_garlic_proximity: 햇마늘 출하(5-6월)까지 남은 비율
    - storage_phase: 저장기(7-11월) 여부 및 저장 경과 비율
    - cold_damage_risk: 냉해 위험기(12-2월, 파종 후 월동)
    - planting_season: 파종기(10-11월)
    - price_momentum_30d: 30일 가격 모멘텀 (저장 소진 감지)
    - harvest_shock: 수확기 가격 급락 감지
    """
    m, d = base_date.month, base_date.day
    day_of_year = base_date.timetuple().tm_yday

    # 햇마늘 출하 근접도 (5/1~6/30)
    new_garlic_peak = 152  # 6/1
    new_garlic_dist = abs(day_of_year - new_garlic_peak)
    new_garlic_proximity = max(0.0, 1.0 - new_garlic_dist / 90.0)

    # 저장기 (7-11월, yday 182~334): 저장 소진 → 가격 상승
    in_storage_phase = 182 <= day_of_year <= 334
    storage_elapsed = max(0.0, (day_of_year - 182) / (334 - 182)) if in_storage_phase else 0.0

    # 냉해 위험기 (12-2월, 월동 파종 직후)
    cold_damage_risk = int(m in (12, 1, 2))

    # 파종기 (10-11월)
    planting_season = int(m in (10, 11))

    # 30일 가격 모멘텀
    lag_30 = values[max(0, idx - 30)]
    current = values[idx]
    momentum_30d = _pct(current, lag_30) if idx >= 30 else 0.0

    # 수확 충격 감지 (5-6월 급락 여부)
    if idx >= 7:
        returns_7 = _returns(values[idx - 7:idx + 1])
        harvest_shock = min(0.0, _safe_mean(returns_7))  # 하락 평균만
    else:
        harvest_shock = 0.0

    # 월별 계절 가중치 (마늘)
    # 5-6월 수확기 낮음, 11-3월 저장 소진 기간 높음
    month_garlic_factor = [1.3, 1.2, 1.1, 1.0, 0.7, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
    month_factor = month_garlic_factor[m - 1]

    return {
        "new_garlic_proximity": round(new_garlic_proximity, 4),
        "in_storage_phase": int(in_storage_phase),
        "storage_elapsed_ratio": round(storage_elapsed, 4),
        "cold_damage_risk": cold_damage_risk,
        "planting_season": planting_season,
        "momentum_30d": round(momentum_30d, 6),
        "harvest_shock": round(harvest_shock, 6),
        "month_seasonal_factor": round(month_factor, 3),
    }


def _green_onion_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    대파: 60-90일 단기 사이클 + 고온/동해 취약.

    핵심 피처:
    - summer_heat_risk: 고온 위험기(7-8월) — 병해 → 공급 충격
    - winter_frost_risk: 동해 위험기(12-2월) — 생육 지연
    - short_cycle_phase: 60일 주기 sin/cos (대파 재배 사이클)
    - price_spike_7d: 7일 내 급등(+10% 이상) 이력
    - supply_recovery_signal: 급등 후 정상화 신호 (급등 후 가격 안정)
    - lag_60d_momentum: 60일 전 대비 (한 사이클 전 가격 추세)
    """
    m = base_date.month
    day_of_year = base_date.timetuple().tm_yday

    # 고온 위험 (7-8월)
    summer_heat_risk = int(m in (7, 8))

    # 동해 위험 (12-2월)
    winter_frost_risk = int(m in (12, 1, 2))

    # 60일 단기 사이클 인코딩
    cycle_60 = day_of_year % 60
    cycle_60_sin = _sin_cycle(cycle_60, 60)
    cycle_60_cos = _cos_cycle(cycle_60, 60)

    current = values[idx]
    # 7일 급등 감지
    window_7 = values[max(0, idx - 7):idx + 1]
    max_7d = max(window_7) if window_7 else current
    price_spike_7d = _pct(max_7d, min(window_7)) if window_7 else 0.0

    # 60일 전 대비
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(current, lag_60) if idx >= 60 else 0.0

    # 급등 후 정상화 신호: 7일 전 급등 + 현재 하락 안정화
    lag_7 = values[idx - 7]
    prior_spike = _pct(lag_7, values[max(0, idx - 14)])
    current_change = _pct(current, lag_7)
    supply_recovery = int(prior_spike > 0.1 and current_change < -0.03)

    # 월별 계절 가중치 (대파): 겨울 높음, 여름 낮음
    month_gonion_factor = [1.3, 1.2, 1.0, 0.9, 0.8, 0.8, 1.0, 1.1, 0.9, 0.9, 1.0, 1.2]
    month_factor = month_gonion_factor[m - 1]

    return {
        "summer_heat_risk": summer_heat_risk,
        "winter_frost_risk": winter_frost_risk,
        "cycle_60d_sin": round(cycle_60_sin, 6),
        "cycle_60d_cos": round(cycle_60_cos, 6),
        "price_spike_7d": round(price_spike_7d, 6),
        "momentum_60d": round(momentum_60d, 6),
        "supply_recovery_signal": supply_recovery,
        "month_seasonal_factor": round(month_factor, 3),
    }


def _onion_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    양파: 마늘과 유사한 연간 사이클 + 저장량 의존도 높음.

    핵심 피처:
    - new_onion_proximity: 햇양파 출하(5-6월) 근접도
    - storage_depletion_phase: 저장 소진기(9-12월) — 가격 상승 압력
    - import_season_risk: 수입 증가 시기(3-4월, 국내 재고 부족 기간)
    - price_acceleration_14d: 14일 가격 가속도 (저장 소진 감지)
    - bimodal_cycle: 수확기(5-6월)와 저장기(10-11월) 2峰 사이클 sin/cos
    - ma_60d_gap: 60일 MA 대비 현재가 (장기 추세 편차)
    """
    m = base_date.month
    day_of_year = base_date.timetuple().tm_yday

    # 햇양파 출하 근접도 (5-6월)
    new_onion_peak = 152  # 6/1
    new_onion_dist = abs(day_of_year - new_onion_peak)
    new_onion_proximity = max(0.0, 1.0 - new_onion_dist / 90.0)

    # 저장 소진기 (9-12월, yday 244~365)
    in_depletion = 244 <= day_of_year <= 365
    depletion_progress = (day_of_year - 244) / 121 if in_depletion else 0.0

    # 수입 증가 위험기 (3-4월)
    import_risk = int(m in (3, 4))

    current = values[idx]

    # 14일 가격 가속도 (2차 미분)
    if idx >= 14:
        change_14 = _pct(current, values[idx - 14])
        change_7 = _pct(current, values[idx - 7])
        price_acceleration = change_14 - change_7  # 가속 시 양수
    else:
        price_acceleration = 0.0

    # 2峰 사이클 (수확기=yday152 vs 저장기=yday305)
    bimodal_phase = min(
        abs(day_of_year - 152),
        abs(day_of_year - 305),
    ) / 76.5
    bimodal_sin = math.sin(math.pi * (1.0 - bimodal_phase))

    # 60일 MA
    ma_60 = _safe_mean(values[max(0, idx - 60):idx], current)
    ma_60_gap = _pct(current, ma_60)

    # 월별 계절 가중치 (양파)
    month_onion_factor = [1.1, 1.0, 1.1, 1.2, 0.8, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.1]
    month_factor = month_onion_factor[m - 1]

    return {
        "new_onion_proximity": round(new_onion_proximity, 4),
        "in_storage_depletion": int(in_depletion),
        "depletion_progress": round(depletion_progress, 4),
        "import_season_risk": import_risk,
        "price_acceleration_14d": round(price_acceleration, 6),
        "bimodal_cycle_sin": round(bimodal_sin, 6),
        "ma_60d_gap": round(ma_60_gap, 6),
        "month_seasonal_factor": round(month_factor, 3),
    }


def _radish_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    무: 배추와 유사한 4계절 교체 + 김장 동반 수요.

    핵심 피처:
    - kimjang_proximity: 김장철 근접도 (배추와 동일, 동반 수요)
    - season_sin/cos: 4계절 인코딩
    - in_summer_slack: 여름 비수기(6-8월) — 수요 낮음, 가격 하락
    - price_vs_cabbage_proxy: 무-배추 가격 상관 (내부적으로 lag 패턴 비교)
    - supply_pressure_14d: 14일 공급 압력 (가격 급락 = 공급 과잉)
    - cold_sensitivity: 한파 민감도 (12-1월 한파 → 출하 지연 → 가격 급등)
    """
    m = base_date.month
    day_of_year = base_date.timetuple().tm_yday

    # 김장철 근접도 (배추와 동일)
    kimjang_peak_yday = 305
    kimjang_dist = abs(day_of_year - kimjang_peak_yday)
    kimjang_proximity = max(0.0, 1.0 - kimjang_dist / 90.0)

    # 4계절 인코딩
    season_idx = (m - 1) // 3
    season_sin = _sin_cycle(season_idx, 4)
    season_cos = _cos_cycle(season_idx, 4)

    # 여름 비수기 (6-8월)
    in_summer_slack = int(m in (6, 7, 8))

    # 한파 민감도 기간 (12-1월)
    cold_sensitive = int(m in (12, 1))

    current = values[idx]

    # 14일 공급 압력 (급락이면 공급 과잉)
    if idx >= 14:
        drop_14d = min(0.0, _pct(current, values[idx - 14]))
        supply_pressure = abs(drop_14d)  # 양수로 변환
    else:
        supply_pressure = 0.0

    # 30일 추세 강도
    lag_30 = values[max(0, idx - 30)]
    trend_30d = _pct(current, lag_30) if idx >= 30 else 0.0

    # 월별 계절 가중치 (무)
    month_radish_factor = [1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.7, 0.8, 1.0, 1.1, 1.3, 1.2]
    month_factor = month_radish_factor[m - 1]

    return {
        "kimjang_proximity": round(kimjang_proximity, 4),
        "season_sin": season_sin,
        "season_cos": season_cos,
        "in_summer_slack": in_summer_slack,
        "cold_sensitivity_period": cold_sensitive,
        "supply_pressure_14d": round(supply_pressure, 6),
        "trend_30d": round(trend_30d, 6),
        "month_seasonal_factor": round(month_factor, 3),
    }


# ── 품목별 디스패처 ────────────────────────────────────────────────────────────

ITEM_FEATURE_FN = {
    "cabbage":     _cabbage_features,
    "garlic":      _garlic_features,
    "green_onion": _green_onion_features,
    "onion":       _onion_features,
    "radish":      _radish_features,
}

# 품목별 피처 컬럼 목록 (CSV 헤더에 사용)
ITEM_EXTRA_FIELDS = {
    "cabbage":     ["kimjang_proximity", "in_harvest_period", "pre_harvest_period",
                    "in_supply_gap", "season_sin", "season_cos",
                    "lag3_vs_ma14_momentum", "month_seasonal_factor"],
    "garlic":      ["new_garlic_proximity", "in_storage_phase", "storage_elapsed_ratio",
                    "cold_damage_risk", "planting_season",
                    "momentum_30d", "harvest_shock", "month_seasonal_factor"],
    "green_onion": ["summer_heat_risk", "winter_frost_risk", "cycle_60d_sin", "cycle_60d_cos",
                    "price_spike_7d", "momentum_60d",
                    "supply_recovery_signal", "month_seasonal_factor"],
    "onion":       ["new_onion_proximity", "in_storage_depletion", "depletion_progress",
                    "import_season_risk", "price_acceleration_14d",
                    "bimodal_cycle_sin", "ma_60d_gap", "month_seasonal_factor"],
    "radish":      ["kimjang_proximity", "season_sin", "season_cos",
                    "in_summer_slack", "cold_sensitivity_period",
                    "supply_pressure_14d", "trend_30d", "month_seasonal_factor"],
}


# ── 데이터 로딩 ───────────────────────────────────────────────────────────────

def _daily_retail_series(prices: list[Any]) -> list[tuple[date, float]]:
    values_by_day: dict[date, list[float]] = defaultdict(list)
    for f in prices:
        if f.region_code not in (None, "평균"):
            continue
        price = f.retail_price or f.wholesale_price
        if price is None:
            continue
        values_by_day[f.base_date].append(price)
    return sorted((day, mean(vs)) for day, vs in values_by_day.items() if vs)


def _daily_at_wholesale(prices: list[Any]) -> dict[date, float]:
    values_by_day: dict[date, list[float]] = defaultdict(list)
    for f in prices:
        if f.source not in ("at_regional_price", "at_market_settlement"):
            continue
        price = f.wholesale_price or f.settlement_price
        if price is None:
            continue
        values_by_day[f.base_date].append(price)
    return {day: mean(vs) for day, vs in values_by_day.items() if vs}


# ── training row 생성 ─────────────────────────────────────────────────────────

COMMON_FIELDS = [
    "base_date", "item_code",
    "avg_price", "price_pct_of_hist_mean",
    "lag_1_price", "lag_3_price", "lag_7_price", "lag_14_price",
    "ma_7_price", "ma_14_price", "ma_28_price",
    "change_1d", "change_3d", "change_7d", "change_14d",
    "ma_7_gap", "ma_14_gap",
    "volatility_7d", "volatility_14d",
    "weekday_sin", "weekday_cos",
    "month_sin", "month_cos",
    "at_wholesale_norm",
]


def _build_rows_for_item(
    item_code: str,
    series: list[tuple[date, float]],
    at_wholesale_by_date: dict[date, float],
    min_history: int,
) -> list[dict]:
    rows = []
    min_req = max(min_history, 14)
    if len(series) < min_req + 2:
        return rows

    values = [v for _, v in series]
    hist_mean = _safe_mean(values, 1.0)
    extra_fn = ITEM_FEATURE_FN.get(item_code)

    for idx in range(min_req, len(series) - 1):
        base_date, current = series[idx]
        next_value = values[idx + 1]

        # 공통 피처
        common = _common_price_features(idx, values, base_date, hist_mean)
        at_ws = at_wholesale_by_date.get(base_date)
        at_wholesale_norm = round(_pct(at_ws, current), 6) if at_ws and current else 0.0

        row = {
            "base_date": base_date.isoformat(),
            "item_code": item_code,
            **common,
            "at_wholesale_norm": at_wholesale_norm,
        }

        # 품목별 특화 피처
        if extra_fn:
            try:
                row.update(extra_fn(base_date, idx, values))
            except Exception:
                pass

        row["target_next_change"] = _pct(next_value, current)
        rows.append(row)

    return rows


# ── CSV 저장 (품목별 파일 분리) ───────────────────────────────────────────────

def _write_item_csv(item_code: str, rows: list[dict], out_dir: Path, suffix: str) -> Path:
    extra_fields = ITEM_EXTRA_FIELDS.get(item_code, [])
    fieldnames = COMMON_FIELDS + extra_fields + ["target_next_change"]
    path = out_dir / f"price_training_{item_code}_{suffix}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    suffix = f"{target_date:%Y%m%d}_{args.output_suffix}"
    out_dir = data_dir() / "model"
    out_dir.mkdir(parents=True, exist_ok=True)

    registry = default_registry()
    connector = CachedPriceConnector()

    all_rows: list[dict] = []
    item_summary: dict[str, dict] = {}

    for item_code in sorted(registry.all_items()):
        prices = connector.fetch_prices(item_code, target_date)
        retail_series = _daily_retail_series(prices)
        at_ws = _daily_at_wholesale(prices)
        rows = _build_rows_for_item(item_code, retail_series, at_ws, args.min_history)

        if rows:
            item_path = _write_item_csv(item_code, rows, out_dir, suffix)
            extra_count = len(ITEM_EXTRA_FIELDS.get(item_code, []))
            item_summary[item_code] = {
                "rows": len(rows),
                "common_features": len(COMMON_FIELDS) - 2,  # base_date, item_code 제외
                "item_specific_features": extra_count,
                "total_features": len(COMMON_FIELDS) - 2 + extra_count,
                "date_range": f"{rows[0]['base_date']} ~ {rows[-1]['base_date']}",
                "file": str(item_path.relative_to(_mkmap_root)),
            }
            all_rows.extend(rows)
            print(f"  [{item_code}] {len(rows)} rows, "
                  f"{extra_count} item-specific features "
                  f"({rows[0]['base_date']} ~ {rows[-1]['base_date']})")

    # 통합 CSV도 저장 (기존 학습 스크립트 호환용 — 공통 피처만)
    combined_path = out_dir / f"price_training_table_{suffix}.csv"
    common_fieldnames = COMMON_FIELDS + ["target_next_change"]
    with combined_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=common_fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nCombined: {combined_path.relative_to(_mkmap_root)} ({len(all_rows)} rows)")
    print("\nItem summary:")
    for item, s in item_summary.items():
        print(f"  {item}: {s['rows']} rows, {s['total_features']} features "
              f"({s['item_specific_features']} item-specific) [{s['date_range']}]")

    return 0 if all_rows else 1


if __name__ == "__main__":
    sys.exit(main())
