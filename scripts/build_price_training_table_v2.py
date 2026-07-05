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
from scripts.farmmap_capacity_features import (
    FARMMAP_FEATURE_COLUMNS,
    default_farmmap_capacity_features,
    load_farmmap_capacity_features_by_item,
)


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
    - bimodal_cycle: 수확기(5-6월)와 저장기(10-11월) 2봉 사이클 sin/cos
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

    # 2봉 사이클 (수확기=yday152 vs 저장기=yday305)
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


def _potato_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    감자: 봄감자(5-6월 고랭지) + 가을감자(10-11월 평지) 이모작.
    저장 감자 출하(1-4월) → 재고 소진 시 가격 급등.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 봄 수확기 근접도 (yday 135~181)
    spring_harvest_prox = max(0.0, 1.0 - abs(d - 158) / 60.0)
    # 가을 수확기 근접도 (yday 274~319)
    fall_harvest_prox = max(0.0, 1.0 - abs(d - 296) / 55.0)
    in_spring_harvest = 135 <= d <= 181
    in_fall_harvest = 274 <= d <= 319
    # 저장 소진기 (1-4월) — 봄 수확 전 재고 부족
    storage_depletion = int(m in (1, 2, 3, 4))
    storage_depletion_progress = max(0.0, (d - 1) / 120.0) if m <= 4 else 0.0
    # 여름 고랭지 프리미엄기 (7-8월, 봄감자 출하 후 가격 안정)
    highland_season = int(m in (7, 8))
    # 30일 모멘텀 (저장 소진 감지)
    lag_30 = values[max(0, idx - 30)]
    momentum_30d = _pct(values[idx], lag_30) if idx >= 30 else 0.0
    mf = [1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.9, 1.0, 1.0, 0.9, 0.9, 1.1][m - 1]
    return {
        "spring_harvest_prox": round(spring_harvest_prox, 4),
        "fall_harvest_prox": round(fall_harvest_prox, 4),
        "in_spring_harvest": int(in_spring_harvest),
        "in_fall_harvest": int(in_fall_harvest),
        "storage_depletion_phase": storage_depletion,
        "storage_depletion_progress": round(storage_depletion_progress, 4),
        "highland_premium_season": highland_season,
        "momentum_30d": round(momentum_30d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _sweet_potato_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    고구마: 9-11월 수확 집중 + 큐어링(후숙) 기간 후 본격 출하(11월~).
    저장 소진기(3-5월) 가격 급등 패턴.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 수확기 (9-11월, yday 244~319)
    in_harvest = 244 <= d <= 319
    # 큐어링 완료 후 본격 출하 (11-12월)
    peak_supply = int(m in (11, 12))
    # 저장 소진기 (3-5월)
    in_depletion = int(m in (3, 4, 5))
    depletion_progress = max(0.0, (d - 60) / 90.0) if 60 <= d <= 150 else 0.0
    # 명절 수요 (추석, 설): 8월말-9월초 / 1-2월
    chuseok_prox = max(0.0, 1.0 - abs(d - 263) / 45.0)  # 추석 근접 (9/20 기준)
    seollal_prox = max(0.0, 1.0 - abs(d - 25) / 30.0)    # 설 근접
    gift_season_prox = max(chuseok_prox, seollal_prox)
    # 30일 모멘텀
    lag_30 = values[max(0, idx - 30)]
    momentum_30d = _pct(values[idx], lag_30) if idx >= 30 else 0.0
    mf = [1.2, 1.1, 1.3, 1.2, 1.0, 0.9, 0.8, 0.9, 1.0, 0.9, 0.9, 1.0][m - 1]
    return {
        "in_harvest_period": int(in_harvest),
        "peak_supply_period": peak_supply,
        "storage_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "gift_season_proximity": round(gift_season_prox, 4),
        "momentum_30d": round(momentum_30d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _tomato_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    토마토: 주로 온실 재배. 봄(3-5월) / 가을(9-11월) 2회 피크.
    여름(6-8월) 고온기 온실 비용 증가 → 가격 상승.
    겨울(12-2월) 난방비 부담 → 가격 최고점.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 봄 성수기 (3-5월)
    spring_peak = max(0.0, 1.0 - abs(d - 105) / 60.0)
    # 가을 성수기 (9-11월)
    fall_peak = max(0.0, 1.0 - abs(d - 289) / 60.0)
    season_peak = max(spring_peak, fall_peak)
    # 여름 고온기 공급 부담 (6-8월)
    summer_supply_stress = int(m in (6, 7, 8))
    # 겨울 난방비 부담 (12-2월)
    winter_heating_cost = int(m in (12, 1, 2))
    # 단기 가격 가속도 (7일)
    if idx >= 7:
        chg7 = _pct(values[idx], values[idx - 7])
        chg14 = _pct(values[idx], values[idx - 14]) if idx >= 14 else chg7
        acceleration = chg7 - chg14 / 2
    else:
        acceleration = 0.0
    mf = [1.3, 1.2, 1.0, 0.9, 0.9, 1.0, 1.1, 1.1, 0.9, 0.9, 1.1, 1.3][m - 1]
    return {
        "season_peak_proximity": round(season_peak, 4),
        "summer_supply_stress": summer_supply_stress,
        "winter_heating_cost": winter_heating_cost,
        "price_acceleration_7d": round(acceleration, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _pepper_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    건고추: 8-9월 수확 → 건조 후 10-11월 본격 출하. 연간 1회 생산.
    재고 소진기(5-7월) 가격 급등. 수입산 대체재 영향 큼.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 수확기 (8-9월, yday 213~273)
    in_harvest = 213 <= d <= 273
    # 건조·본격 출하기 (10-11월)
    peak_supply = int(m in (10, 11))
    # 재고 소진기 (5-7월) — 다음 수확 전 가격 최고점
    in_depletion = int(m in (5, 6, 7))
    depletion_progress = max(0.0, (d - 120) / 92.0) if 120 <= d <= 212 else 0.0
    # 수입 위험기 (4-7월: 국내 재고 부족 → 수입 대체)
    import_risk = int(m in (4, 5, 6, 7))
    # 60일 모멘텀 (연간 주기 추세)
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [1.1, 1.1, 1.2, 1.2, 1.3, 1.3, 1.2, 0.9, 0.8, 0.9, 1.0, 1.1][m - 1]
    return {
        "in_harvest_period": int(in_harvest),
        "peak_supply_period": peak_supply,
        "stock_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "import_substitution_risk": import_risk,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _fresh_pepper_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    붉은고추(생고추): 여름 노지 재배 중심. 7-9월 집중 출하 → 가격 최저.
    겨울(12-3월) 온실 생산 원가 높아 가격 최고.
    여름 고온·폭우 = 병해 위험.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 여름 노지 집중 출하기 (7-9월) — 가격 최저
    in_peak_supply = int(m in (7, 8, 9))
    supply_proximity = max(0.0, 1.0 - abs(d - 228) / 75.0)
    # 겨울 온실 원가 부담 (12-3월)
    winter_cost_burden = int(m in (12, 1, 2, 3))
    # 고온 병해 위험 (7-8월)
    heat_disease_risk = int(m in (7, 8))
    # 봄 이식기 (3-4월) — 작황 예고 구간
    planting_period = int(m in (3, 4))
    # 7일 가격 모멘텀
    lag_7 = values[idx - 7]
    spike_7d = _pct(values[idx], lag_7) if idx >= 7 else 0.0
    mf = [1.3, 1.2, 1.1, 1.0, 1.0, 0.9, 0.7, 0.7, 0.8, 1.0, 1.1, 1.3][m - 1]
    return {
        "in_peak_supply": in_peak_supply,
        "supply_season_proximity": round(supply_proximity, 4),
        "winter_cost_burden": winter_cost_burden,
        "heat_disease_risk": heat_disease_risk,
        "planting_period": planting_period,
        "spike_7d": round(spike_7d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _cucumber_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    오이: 온실 주년 생산. 여름(6-8월) 노지 출하 증가 → 가격 하락.
    봄(3-5월) / 가을(9-11월) 온실 성수기.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 봄 성수기 (3-5월)
    spring_peak = max(0.0, 1.0 - abs(d - 105) / 55.0)
    # 가을 성수기 (9-11월)
    fall_peak = max(0.0, 1.0 - abs(d - 289) / 55.0)
    season_peak = max(spring_peak, fall_peak)
    # 여름 공급 과잉 (6-8월) — 노지 대량 출하
    summer_oversupply = int(m in (6, 7, 8))
    # 겨울 난방비 원가 (12-2월)
    winter_heating_cost = int(m in (12, 1, 2))
    # 단기 변동성 (오이는 가격 변동 빠름)
    if idx >= 7:
        returns_7 = _returns(values[max(0, idx - 7):idx + 1])
        vol_7d = _safe_std(returns_7)
    else:
        vol_7d = 0.0
    mf = [1.2, 1.2, 1.0, 0.9, 0.9, 1.0, 1.1, 1.0, 0.9, 0.9, 1.0, 1.2][m - 1]
    return {
        "season_peak_proximity": round(season_peak, 4),
        "summer_oversupply": summer_oversupply,
        "winter_heating_cost": winter_heating_cost,
        "extra_volatility_7d": round(vol_7d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _carrot_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    당근: 제주(10-12월 수확) + 강원 고랭지(8-9월) 이원 생산.
    제주 당근이 전국 공급량의 60% 이상 차지.
    저장 소진기(3-6월) 가격 급등.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 제주 수확 근접도 (10-12월)
    jeju_harvest_prox = max(0.0, 1.0 - abs(d - 305) / 75.0)
    in_jeju_harvest = 274 <= d <= 366
    # 강원 고랭지 수확 (8-9월)
    highland_harvest = int(m in (8, 9))
    # 저장 소진기 (3-6월) — 제주 수확 전 재고 최저
    in_depletion = int(m in (3, 4, 5, 6))
    depletion_progress = max(0.0, (d - 60) / 121.0) if 60 <= d <= 181 else 0.0
    # 겨울 제주 출하 성수기 (1-2월)
    peak_supply = int(m in (1, 2))
    # 60일 모멘텀
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [0.9, 0.9, 1.1, 1.2, 1.3, 1.2, 1.0, 0.9, 0.9, 1.0, 1.0, 0.9][m - 1]
    return {
        "jeju_harvest_proximity": round(jeju_harvest_prox, 4),
        "in_jeju_harvest": int(in_jeju_harvest),
        "highland_harvest_period": highland_harvest,
        "storage_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "peak_supply_period": peak_supply,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _apple_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    사과: 수확(9-11월) 후 저장 출하. 추석 수요 최대.
    후지 품종 기준 11월~다음해 7월 저장 출하.
    저장 소진기(6-8월) 가격 최고.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 추석 근접도 (9월 중순, yday 258 기준)
    chuseok_prox = max(0.0, 1.0 - abs(d - 258) / 45.0)
    # 설날 근접도 (1월 말, yday 25 기준)
    seollal_prox = max(0.0, 1.0 - abs(d - 25) / 30.0)
    gift_season_prox = max(chuseok_prox, seollal_prox)
    # 수확기 (9-11월)
    in_harvest = 244 <= d <= 334
    # 저장 출하기 (12-7월)
    in_storage_supply = not in_harvest
    # 저장 소진기 (6-8월) — 수확 전 재고 최저
    in_depletion = int(m in (6, 7, 8))
    depletion_progress = max(0.0, (d - 152) / 92.0) if 152 <= d <= 244 else 0.0
    # 동해·냉해 위험기 (꽃피기 직후, 4-5월 늦서리)
    late_frost_risk = int(m in (4, 5))
    # 60일 모멘텀 (저장 소진 추세)
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [1.1, 1.1, 1.0, 1.0, 1.0, 1.1, 1.2, 1.2, 1.0, 0.9, 0.9, 1.1][m - 1]
    return {
        "chuseok_proximity": round(chuseok_prox, 4),
        "gift_season_proximity": round(gift_season_prox, 4),
        "in_harvest_period": int(in_harvest),
        "storage_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "late_frost_risk": late_frost_risk,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _pear_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    배: 추석 수요 집중(8-9월 수확). 신고 품종 기준.
    배는 저장성이 사과보다 낮아 수확 후 3-4개월 내 출하.
    수확기(8-9월) 직전 가격 최고 → 수확 후 급락 패턴.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 추석 근접도 (8월말-9월초, yday 244 기준)
    chuseok_prox = max(0.0, 1.0 - abs(d - 244) / 50.0)
    # 수확 직전 가격 상승기 (7-8월 초)
    pre_harvest_premium = max(0.0, 1.0 - abs(d - 213) / 45.0)
    # 수확기 (8-10월, yday 213~304)
    in_harvest = 213 <= d <= 304
    # 저장 소진기 (4-7월)
    in_depletion = int(m in (4, 5, 6, 7))
    depletion_progress = max(0.0, (d - 90) / 120.0) if 90 <= d <= 210 else 0.0
    # 늦서리 위험 (4월 개화기)
    blossom_frost_risk = int(m == 4)
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [1.0, 1.0, 1.0, 1.0, 1.1, 1.2, 1.2, 1.0, 0.9, 0.9, 1.0, 1.0][m - 1]
    return {
        "chuseok_proximity": round(chuseok_prox, 4),
        "pre_harvest_premium": round(pre_harvest_premium, 4),
        "in_harvest_period": int(in_harvest),
        "storage_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "blossom_frost_risk": blossom_frost_risk,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _watermelon_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    수박: 여름(6-8월) 최대 수요·공급. 초여름(5-6월) 가격 최고.
    봄 촉성 재배(4-5월 하우스) → 여름 노지 출하(6-8월) 가격 하락.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 수요 최성기 근접도 (7월 중순, yday 196 기준)
    peak_demand_prox = max(0.0, 1.0 - abs(d - 196) / 60.0)
    # 초여름 하우스 출하 시작 (5-6월) — 가격 최고
    early_supply_prox = max(0.0, 1.0 - abs(d - 150) / 45.0)
    # 여름 노지 대량 출하 (7-8월) — 가격 하락
    in_peak_supply = int(m in (7, 8))
    # 비수기 (10-4월) — 하우스 재배, 공급 적음
    in_offseason = int(m in (10, 11, 12, 1, 2, 3, 4))
    # 폭염 수요 증가 신호 (7-8월 전주 기온 상관)
    summer_heat_demand = int(m in (7, 8))
    lag_14 = values[idx - 14] if idx >= 14 else values[0]
    momentum_14d = _pct(values[idx], lag_14) if idx >= 14 else 0.0
    mf = [1.0, 1.0, 1.0, 1.1, 1.3, 1.2, 0.9, 0.8, 1.0, 1.1, 1.1, 1.0][m - 1]
    return {
        "peak_demand_proximity": round(peak_demand_prox, 4),
        "early_supply_proximity": round(early_supply_prox, 4),
        "in_peak_supply": in_peak_supply,
        "in_offseason": in_offseason,
        "summer_heat_demand": summer_heat_demand,
        "momentum_14d": round(momentum_14d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _strawberry_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    딸기: 역계절 작물. 가을 정식(9-10월) → 겨울 출하(11-4월) 최성기.
    발렌타인데이(2/14) / 화이트데이(3/14) 수요 스파이크.
    여름(6-8월)은 완전 비수기.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 겨울 성수기 근접도 (12-2월)
    winter_peak_prox = max(0.0, 1.0 - min(
        abs(d - 15),   # 1/15
        abs(d - 365 + 15)
    ) / 90.0)
    # 발렌타인/화이트데이 수요 (2월 초~3월 중순, yday 32~73)
    gift_day_prox = max(0.0, 1.0 - abs(d - 52) / 45.0)
    # 본격 출하기 (11-3월)
    in_peak_supply = int(m in (11, 12, 1, 2, 3))
    # 여름 완전 비수기 (6-8월) — 하우스 정식 준비
    in_offseason = int(m in (6, 7, 8))
    # 가을 정식기 (9-10월) — 가격 예고 구간
    planting_period = int(m in (9, 10))
    # 4월 이후 물량 감소 → 가격 반등
    supply_taper = max(0.0, (d - 90) / 60.0) if 90 <= d <= 150 else 0.0
    lag_14 = values[idx - 14] if idx >= 14 else values[0]
    momentum_14d = _pct(values[idx], lag_14) if idx >= 14 else 0.0
    mf = [1.2, 1.3, 1.2, 1.0, 0.9, 0.7, 0.6, 0.6, 0.8, 1.0, 1.2, 1.3][m - 1]
    return {
        "winter_peak_proximity": round(winter_peak_prox, 4),
        "gift_day_proximity": round(gift_day_prox, 4),
        "in_peak_supply": in_peak_supply,
        "in_offseason": in_offseason,
        "planting_period": planting_period,
        "supply_taper": round(supply_taper, 4),
        "momentum_14d": round(momentum_14d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _grape_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    포도: 8-10월 수확 집중. 추석 선물 수요 큼.
    거봉/캠벨 8-9월, 샤인머스캣 9-10월.
    겨울·봄은 수입산 의존도 증가.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 추석 근접도 (9월 중순, yday 258 기준)
    chuseok_prox = max(0.0, 1.0 - abs(d - 258) / 45.0)
    # 수확기 (8-10월, yday 213~304)
    in_harvest = 213 <= d <= 304
    # 수확 직전 최고가 구간 (7월, yday 182~212)
    pre_harvest_premium = max(0.0, 1.0 - abs(d - 197) / 30.0)
    # 비수기 수입 의존기 (12-6월)
    import_dependency = int(m in (12, 1, 2, 3, 4, 5, 6))
    # 저온 창고 재고 소진 (4-7월)
    in_depletion = int(m in (4, 5, 6, 7))
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [1.0, 1.0, 1.0, 1.0, 1.1, 1.1, 1.2, 1.1, 1.0, 1.0, 1.0, 1.0][m - 1]
    return {
        "chuseok_proximity": round(chuseok_prox, 4),
        "in_harvest_period": int(in_harvest),
        "pre_harvest_premium": round(pre_harvest_premium, 4),
        "import_dependency_period": import_dependency,
        "storage_depletion_phase": in_depletion,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _zucchini_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    애호박: 온실 주년 생산. 여름(6-8월) 고온 공급 스트레스.
    봄(4-5월) / 가을(9-10월) 성수기.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    spring_peak = max(0.0, 1.0 - abs(d - 120) / 50.0)
    fall_peak = max(0.0, 1.0 - abs(d - 274) / 50.0)
    season_peak = max(spring_peak, fall_peak)
    summer_stress = int(m in (6, 7, 8))
    winter_cost = int(m in (12, 1, 2))
    if idx >= 7:
        vol = _safe_std(_returns(values[max(0, idx - 7):idx + 1]))
    else:
        vol = 0.0
    mf = [1.2, 1.1, 1.0, 0.9, 0.9, 1.0, 1.1, 1.0, 0.9, 0.9, 1.0, 1.2][m - 1]
    return {
        "season_peak_proximity": round(season_peak, 4),
        "summer_supply_stress": summer_stress,
        "winter_cost_burden": winter_cost,
        "short_cycle_volatility": round(vol, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _spinach_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    시금치: 겨울 노지(남해안) 최고 품질. 봄·가을 성수기.
    여름(6-8월) 고온 취약 → 공급 급감 → 가격 급등.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 겨울 노지 성수기 (11-2월)
    winter_quality_peak = max(0.0, 1.0 - min(abs(d - 350), abs(d - 365 + 350)) / 90.0)
    # 봄 성수기 (3-4월)
    spring_peak = max(0.0, 1.0 - abs(d - 90) / 45.0)
    season_quality = max(winter_quality_peak, spring_peak)
    # 여름 공급 충격 위험 (6-8월)
    summer_shock_risk = int(m in (6, 7, 8))
    # 한파 출하 지연 (1-2월 강추위)
    cold_supply_delay = int(m in (1, 2))
    spike_7d = _pct(values[idx], values[idx - 7]) if idx >= 7 else 0.0
    mf = [1.1, 1.2, 1.1, 1.0, 0.9, 1.0, 1.2, 1.2, 1.0, 0.9, 1.0, 1.1][m - 1]
    return {
        "seasonal_quality_peak": round(season_quality, 4),
        "summer_supply_shock_risk": summer_shock_risk,
        "cold_supply_delay": cold_supply_delay,
        "price_spike_7d": round(spike_7d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _lettuce_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    상추: 60일 초단기 생육. 여름 삼겹살 수요 최고.
    여름 고온 공급 차질 → 수요·공급 동시 피크 → 가격 급등락.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 삼겹살 수요 성수기 (5-8월)
    bbq_demand = int(m in (5, 6, 7, 8))
    bbq_peak_prox = max(0.0, 1.0 - abs(d - 196) / 75.0)
    # 여름 고온 공급 스트레스 (7-8월) — 수요는 높은데 공급 불안정
    summer_supply_stress = int(m in (7, 8))
    # 겨울 난방비 (12-2월)
    winter_cost = int(m in (12, 1, 2))
    # 60일 사이클 (재배 주기)
    cycle_phase = d % 60
    cycle_sin = _sin_cycle(cycle_phase, 60)
    # 단기 변동성 (상추는 가격 변동 매우 빠름)
    if idx >= 7:
        vol = _safe_std(_returns(values[max(0, idx - 7):idx + 1]))
        spike = _pct(values[idx], values[idx - 7])
    else:
        vol = 0.0
        spike = 0.0
    mf = [1.1, 1.0, 0.9, 0.9, 1.0, 1.1, 1.2, 1.1, 0.9, 0.9, 1.0, 1.1][m - 1]
    return {
        "bbq_demand_season": bbq_demand,
        "bbq_peak_proximity": round(bbq_peak_prox, 4),
        "summer_supply_stress": summer_supply_stress,
        "winter_cost_burden": winter_cost,
        "short_cycle_sin": round(cycle_sin, 6),
        "volatility_7d_extra": round(vol, 6),
        "spike_7d": round(spike, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _perilla_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    깻잎: 온실 주년 생산. 삼겹살 문화로 상추와 수요 연동.
    여름 고온 시 재배 난이도 증가 → 공급 압박.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    bbq_prox = max(0.0, 1.0 - abs(d - 196) / 75.0)
    summer_stress = int(m in (7, 8))
    winter_cost = int(m in (12, 1, 2))
    if idx >= 7:
        spike = _pct(values[idx], values[idx - 7])
    else:
        spike = 0.0
    mf = [1.1, 1.0, 0.9, 0.9, 1.0, 1.1, 1.2, 1.1, 0.9, 0.9, 1.0, 1.1][m - 1]
    return {
        "bbq_season_proximity": round(bbq_prox, 4),
        "summer_heat_stress": summer_stress,
        "winter_cost_burden": winter_cost,
        "price_spike_7d": round(spike, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _chamoe_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    참외: 성주(경북) 집중 생산(전국 80%). 5-8월 노지 출하 집중.
    5월 초 하우스 출하 시작 → 6-7월 최성기 → 8월 말 종료.
    비수기(10-4월) 하우스 소량 생산.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 성수기 근접도 (6-7월, yday 166 기준)
    peak_prox = max(0.0, 1.0 - abs(d - 196) / 75.0)
    in_peak = int(m in (6, 7))
    in_supply = int(m in (5, 6, 7, 8))
    # 비수기 (10-4월) — 하우스 소량
    in_offseason = int(m in (10, 11, 12, 1, 2, 3, 4))
    # 초여름 가격 하락 가속 (6월)
    early_drop_prox = max(0.0, 1.0 - abs(d - 166) / 30.0)
    lag_14 = values[idx - 14] if idx >= 14 else values[0]
    momentum_14d = _pct(values[idx], lag_14) if idx >= 14 else 0.0
    mf = [1.0, 1.0, 1.0, 1.1, 1.2, 1.0, 0.9, 0.9, 1.1, 1.1, 1.1, 1.0][m - 1]
    return {
        "peak_season_proximity": round(peak_prox, 4),
        "in_peak_season": in_peak,
        "in_supply_season": in_supply,
        "in_offseason": in_offseason,
        "early_drop_proximity": round(early_drop_prox, 4),
        "momentum_14d": round(momentum_14d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


def _sesame_features(base_date: date, idx: int, values: list[float]) -> dict:
    """
    참깨: 8-9월 수확 집중. 연간 1회 생산. 수입 의존도 높음.
    수확 직후(9-10월) 가격 최저 → 소진기(5-7월) 가격 최고.
    """
    m = base_date.month
    d = base_date.timetuple().tm_yday
    # 수확기 (8-9월)
    in_harvest = int(m in (8, 9))
    harvest_prox = max(0.0, 1.0 - abs(d - 243) / 60.0)
    # 재고 소진기 (5-7월)
    in_depletion = int(m in (5, 6, 7))
    depletion_progress = max(0.0, (d - 120) / 92.0) if 120 <= d <= 212 else 0.0
    # 파종기 (4-5월) — 작황 예고
    planting_period = int(m in (4, 5))
    # 수입 가격 연동기 (1-4월, 국내 재고 부족 구간)
    import_linkage = int(m in (1, 2, 3, 4))
    lag_60 = values[max(0, idx - 60)]
    momentum_60d = _pct(values[idx], lag_60) if idx >= 60 else 0.0
    mf = [1.1, 1.1, 1.1, 1.1, 1.2, 1.2, 1.2, 1.0, 0.8, 0.9, 1.0, 1.1][m - 1]
    return {
        "in_harvest_period": in_harvest,
        "harvest_proximity": round(harvest_prox, 4),
        "stock_depletion_phase": in_depletion,
        "depletion_progress": round(depletion_progress, 4),
        "planting_period": planting_period,
        "import_price_linkage": import_linkage,
        "momentum_60d": round(momentum_60d, 6),
        "month_seasonal_factor": round(mf, 3),
    }


# ── 품목별 디스패처 ────────────────────────────────────────────────────────────

ITEM_FEATURE_FN = {
    "cabbage":      _cabbage_features,
    "garlic":       _garlic_features,
    "green_onion":  _green_onion_features,
    "onion":        _onion_features,
    "radish":       _radish_features,
    # 신규 추가 (18개 품목)
    "potato":       _potato_features,
    "sweet_potato": _sweet_potato_features,
    "tomato":       _tomato_features,
    "pepper":       _pepper_features,
    "fresh_pepper": _fresh_pepper_features,
    "cucumber":     _cucumber_features,
    "carrot":       _carrot_features,
    "apple":        _apple_features,
    "pear":         _pear_features,
    "watermelon":   _watermelon_features,
    "strawberry":   _strawberry_features,
    "grape":        _grape_features,
    "zucchini":     _zucchini_features,
    "spinach":      _spinach_features,
    "lettuce":      _lettuce_features,
    "perilla":      _perilla_features,
    "chamoe":       _chamoe_features,
    "sesame":       _sesame_features,
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
    "potato":      ["spring_harvest_prox", "fall_harvest_prox", "in_spring_harvest",
                    "in_fall_harvest", "storage_depletion_phase", "storage_depletion_progress",
                    "highland_premium_season", "momentum_30d", "month_seasonal_factor"],
    "sweet_potato":["in_harvest_period", "peak_supply_period", "storage_depletion_phase",
                    "depletion_progress", "gift_season_proximity",
                    "momentum_30d", "month_seasonal_factor"],
    "tomato":      ["season_peak_proximity", "summer_supply_stress",
                    "winter_heating_cost", "price_acceleration_7d", "month_seasonal_factor"],
    "pepper":      ["in_harvest_period", "peak_supply_period", "stock_depletion_phase",
                    "depletion_progress", "import_substitution_risk",
                    "momentum_60d", "month_seasonal_factor"],
    "fresh_pepper":["in_peak_supply", "supply_season_proximity", "winter_cost_burden",
                    "heat_disease_risk", "planting_period",
                    "spike_7d", "month_seasonal_factor"],
    "cucumber":    ["season_peak_proximity", "summer_oversupply",
                    "winter_heating_cost", "extra_volatility_7d", "month_seasonal_factor"],
    "carrot":      ["jeju_harvest_proximity", "in_jeju_harvest", "highland_harvest_period",
                    "storage_depletion_phase", "depletion_progress",
                    "peak_supply_period", "momentum_60d", "month_seasonal_factor"],
    "apple":       ["chuseok_proximity", "gift_season_proximity", "in_harvest_period",
                    "storage_depletion_phase", "depletion_progress",
                    "late_frost_risk", "momentum_60d", "month_seasonal_factor"],
    "pear":        ["chuseok_proximity", "pre_harvest_premium", "in_harvest_period",
                    "storage_depletion_phase", "depletion_progress",
                    "blossom_frost_risk", "momentum_60d", "month_seasonal_factor"],
    "watermelon":  ["peak_demand_proximity", "early_supply_proximity",
                    "in_peak_supply", "in_offseason",
                    "summer_heat_demand", "momentum_14d", "month_seasonal_factor"],
    "strawberry":  ["winter_peak_proximity", "gift_day_proximity",
                    "in_peak_supply", "in_offseason", "planting_period",
                    "supply_taper", "momentum_14d", "month_seasonal_factor"],
    "grape":       ["chuseok_proximity", "in_harvest_period", "pre_harvest_premium",
                    "import_dependency_period", "storage_depletion_phase",
                    "momentum_60d", "month_seasonal_factor"],
    "zucchini":    ["season_peak_proximity", "summer_supply_stress",
                    "winter_cost_burden", "short_cycle_volatility", "month_seasonal_factor"],
    "spinach":     ["seasonal_quality_peak", "summer_supply_shock_risk",
                    "cold_supply_delay", "price_spike_7d", "month_seasonal_factor"],
    "lettuce":     ["bbq_demand_season", "bbq_peak_proximity", "summer_supply_stress",
                    "winter_cost_burden", "short_cycle_sin",
                    "volatility_7d_extra", "spike_7d", "month_seasonal_factor"],
    "perilla":     ["bbq_season_proximity", "summer_heat_stress",
                    "winter_cost_burden", "price_spike_7d", "month_seasonal_factor"],
    "chamoe":      ["peak_season_proximity", "in_peak_season", "in_supply_season",
                    "in_offseason", "early_drop_proximity",
                    "momentum_14d", "month_seasonal_factor"],
    "sesame":      ["in_harvest_period", "harvest_proximity", "stock_depletion_phase",
                    "depletion_progress", "planting_period",
                    "import_price_linkage", "momentum_60d", "month_seasonal_factor"],
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


def _daily_volume_series(prices: list[Any]) -> dict[date, float]:
    """날짜별 일 거래량 합계."""
    vol_by_day: dict[date, float] = defaultdict(float)
    for f in prices:
        v = getattr(f, "volume", None)
        if v and v > 0:
            vol_by_day[f.base_date] += v
    return dict(vol_by_day)


def _load_weather_series(item_code: str, target_date: date) -> dict[date, dict]:
    """data/features/{date}/kma_crop_weather_{item}.json 전부 스캔 → 날짜별 평균 기상."""
    import json
    features_root = data_dir() / "features"
    result: dict[date, dict] = {}
    for folder in sorted(features_root.iterdir()):
        if not folder.is_dir():
            continue
        jf = folder / f"kma_crop_weather_{item_code}.json"
        if not jf.exists():
            continue
        try:
            rows = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not rows:
            continue
        # 날짜 파싱
        try:
            stamp = folder.name  # YYYYMMDD
            row_date = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        except Exception:
            continue
        if row_date > target_date:
            continue
        # 여러 지역 평균
        temps, rains, humids = [], [], []
        for row in rows:
            if isinstance(row, dict):
                t = row.get("temperature")
                r = row.get("rainfall")
                h = row.get("humidity")
                if t is not None: temps.append(float(t))
                if r is not None: rains.append(float(r))
                if h is not None: humids.append(float(h))
        result[row_date] = {
            "temp": mean(temps) if temps else None,
            "rain": mean(rains) if rains else None,
            "humidity": mean(humids) if humids else None,
        }
    return result


def _weather_features(base_date: date, weather_by_date: dict[date, dict]) -> dict:
    """날짜 기준 7일/30일 rolling 날씨 피처."""
    temps_7, rains_7, humids_7 = [], [], []
    temps_30, rains_30, humids_30 = [], [], []

    for lag in range(1, 31):
        d = base_date - timedelta(days=lag)
        w = weather_by_date.get(d)
        if w is None:
            continue
        if lag <= 7:
            if w.get("temp") is not None: temps_7.append(w["temp"])
            if w.get("rain") is not None: rains_7.append(w["rain"])
            if w.get("humidity") is not None: humids_7.append(w["humidity"])
        if w.get("temp") is not None: temps_30.append(w["temp"])
        if w.get("rain") is not None: rains_30.append(w["rain"])
        if w.get("humidity") is not None: humids_30.append(w["humidity"])

    # 이번달 날씨
    month_temps, month_rains = [], []
    d = date(base_date.year, base_date.month, 1)
    while d < base_date:
        w = weather_by_date.get(d)
        if w:
            if w.get("temp") is not None: month_temps.append(w["temp"])
            if w.get("rain") is not None: month_rains.append(w["rain"])
        d += timedelta(days=1)

    # 전월
    first_of_month = date(base_date.year, base_date.month, 1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = date(last_month_end.year, last_month_end.month, 1)
    prev_temps, prev_rains = [], []
    d = last_month_start
    while d <= last_month_end:
        w = weather_by_date.get(d)
        if w:
            if w.get("temp") is not None: prev_temps.append(w["temp"])
            if w.get("rain") is not None: prev_rains.append(w["rain"])
        d += timedelta(days=1)

    has_weather = bool(temps_7 or temps_30)
    return {
        "weather_available": 1 if has_weather else 0,
        "temp_7d_avg": round(_safe_mean(temps_7, 0.0), 2),
        "rain_7d_sum": round(sum(rains_7), 2),
        "humidity_7d_avg": round(_safe_mean(humids_7, 0.0), 2),
        "temp_30d_avg": round(_safe_mean(temps_30, 0.0), 2),
        "rain_30d_sum": round(sum(rains_30), 2),
        "temp_month_avg": round(_safe_mean(month_temps, 0.0), 2),
        "rain_month_sum": round(sum(month_rains), 2),
        "temp_vs_prev_month": round(
            _pct(_safe_mean(month_temps, 0.0), _safe_mean(prev_temps, 1.0)), 4
        ) if prev_temps and month_temps else 0.0,
        "rain_vs_prev_month": round(
            _pct(sum(month_rains) + 0.1, sum(prev_rains) + 0.1), 4
        ) if prev_rains else 0.0,
    }


def _volume_features(base_date: date, vol_by_date: dict[date, float]) -> dict:
    """날짜 기준 거래량 rolling 피처."""
    vols_7 = [vol_by_date[base_date - timedelta(days=i)]
              for i in range(1, 8) if (base_date - timedelta(days=i)) in vol_by_date]
    vols_30 = [vol_by_date[base_date - timedelta(days=i)]
               for i in range(1, 31) if (base_date - timedelta(days=i)) in vol_by_date]

    # 이번달 누적 거래량
    month_vol = 0.0
    d = date(base_date.year, base_date.month, 1)
    while d < base_date:
        month_vol += vol_by_date.get(d, 0.0)
        d += timedelta(days=1)

    # 전월 거래량
    first_of_month = date(base_date.year, base_date.month, 1)
    last_month_end = first_of_month - timedelta(days=1)
    last_month_start = date(last_month_end.year, last_month_end.month, 1)
    prev_month_vol = 0.0
    d = last_month_start
    while d <= last_month_end:
        prev_month_vol += vol_by_date.get(d, 0.0)
        d += timedelta(days=1)

    today_vol = vol_by_date.get(base_date, 0.0)
    avg_7d = _safe_mean(vols_7, today_vol)
    avg_30d = _safe_mean(vols_30, today_vol)

    return {
        "volume_today": round(today_vol, 2),
        "volume_7d_avg": round(avg_7d, 2),
        "volume_7d_sum": round(sum(vols_7), 2),
        "volume_30d_avg": round(avg_30d, 2),
        "volume_vs_7d_avg": round(_pct(today_vol, avg_7d), 4) if avg_7d else 0.0,
        "volume_month_sum": round(month_vol, 2),
        "volume_vs_prev_month": round(
            _pct(month_vol + 0.1, prev_month_vol + 0.1), 4
        ),
    }


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
    # volume 피처
    "volume_today", "volume_7d_avg", "volume_7d_sum", "volume_30d_avg",
    "volume_vs_7d_avg", "volume_month_sum", "volume_vs_prev_month",
    # weather 피처
    "weather_available",
    "temp_7d_avg", "rain_7d_sum", "humidity_7d_avg",
    "temp_30d_avg", "rain_30d_sum",
    "temp_month_avg", "rain_month_sum",
    "temp_vs_prev_month", "rain_vs_prev_month",
    # FarmMap crop-region support priors
    *FARMMAP_FEATURE_COLUMNS,
]


def _build_rows_for_item(
    item_code: str,
    series: list[tuple[date, float]],
    at_wholesale_by_date: dict[date, float],
    vol_by_date: dict[date, float],
    weather_by_date: dict[date, dict],
    farmmap_features: dict[str, float],
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

        # 공통 가격 피처
        common = _common_price_features(idx, values, base_date, hist_mean)
        at_ws = at_wholesale_by_date.get(base_date)
        at_wholesale_norm = round(_pct(at_ws, current), 6) if at_ws and current else 0.0

        row = {
            "base_date": base_date.isoformat(),
            "item_code": item_code,
            **common,
            "at_wholesale_norm": at_wholesale_norm,
        }
        row.update({
            column: round(float(farmmap_features.get(column, 0.0)), 6)
            for column in FARMMAP_FEATURE_COLUMNS
        })

        # 거래량 피처
        row.update(_volume_features(base_date, vol_by_date))

        # 날씨 피처
        row.update(_weather_features(base_date, weather_by_date))

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
    farmmap_features_by_item = load_farmmap_capacity_features_by_item(_mkmap_root)

    for item_code in sorted(registry.all_items()):
        prices = connector.fetch_prices(item_code, target_date)
        retail_series = _daily_retail_series(prices)
        at_ws = _daily_at_wholesale(prices)
        vol_by_date = _daily_volume_series(prices)
        weather_by_date = _load_weather_series(item_code, target_date)
        farmmap_features = farmmap_features_by_item.get(item_code, default_farmmap_capacity_features())
        rows = _build_rows_for_item(
            item_code, retail_series, at_ws, vol_by_date, weather_by_date, farmmap_features, args.min_history
        )

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
