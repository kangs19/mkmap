"""
품목별 특화 피처 계산기

각 품목의 가격 결정 메커니즘에 맞는 피처를 build_features() 결과에 추가.
입력: features.py의 build_features()가 반환한 DataFrame
출력: 특화 피처 컬럼이 추가된 DataFrame
"""

import numpy as np
import pandas as pd
from datetime import date


# ═══════════════════════════════════════════════════════════════
# 공통 유틸
# ═══════════════════════════════════════════════════════════════

def _month(ts) -> int:
    return ts.month if hasattr(ts, 'month') else pd.Timestamp(ts).month

def _is_between_months(ts, m_start: int, m_end: int) -> bool:
    m = _month(ts)
    if m_start <= m_end:
        return m_start <= m <= m_end
    return m >= m_start or m <= m_end  # 연도 경계 (예: 11~2월)

def _proximity(days_to: float, window: int) -> float:
    """window일 이내 근접도 (0~1, 0=멀다, 1=오늘이 이벤트일)"""
    if pd.isna(days_to):
        return 0.0
    return max(0.0, 1.0 - abs(days_to) / window)

def _safe_col(df: pd.DataFrame, col: str, default=0.0):
    return df[col] if col in df.columns else pd.Series(default, index=df.index)


# ═══════════════════════════════════════════════════════════════
# 배추 (cabbage) 특화 피처
# ═══════════════════════════════════════════════════════════════

def add_cabbage_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dtk = _safe_col(df, "days_to_kimjang")

    # 김장 접근 강도 (30일, 90일 윈도우)
    df["kimjang_urgency_30d"] = dtk.apply(lambda x: _proximity(x, 30))
    df["kimjang_urgency_90d"] = dtk.apply(lambda x: _proximity(x, 90))

    # 계절 구간 (0=봄출하 3~6월, 1=고랭지여름 7~9월, 2=가을출하 10~11월, 3=겨울품귀 12~2월)
    def _phase(ts):
        m = _month(ts)
        if 3 <= m <= 6:   return 0
        if 7 <= m <= 9:   return 1
        if 10 <= m <= 11: return 2
        return 3
    df["cabbage_season_phase"] = [_phase(ts) for ts in df.index]

    # 고랭지 기온 이상 (7~9월에 w_temp_dev가 의미 있음)
    temp_dev = _safe_col(df, "w_temp_dev")
    phase = df["cabbage_season_phase"]
    df["highland_temp_stress"] = np.where(phase == 1, temp_dev.abs(), 0.0)

    # 가을배추 출하기 공급 압박 (10~11월에 거래량 vs 평균)
    mkt_vs = _safe_col(df, "mkt_volume_vs_avg")
    df["autumn_supply_pressure"] = np.where(phase == 2, mkt_vs.fillna(0), 0.0)

    # 김장 시즌 전 30일 가격 변동성
    vol = _safe_col(df, "volatility_14d")
    is_kimjang = _safe_col(df, "is_kimjang_season")
    df["kimjang_vol_spike"] = vol * (is_kimjang + df["kimjang_urgency_30d"])

    # 두 주산지 동시 이상기온 근사 (단일 지역 기온 이상의 제곱으로 근사)
    df["double_region_stress"] = temp_dev.apply(lambda x: x**2 / 10 if not pd.isna(x) else 0.0)

    return df


# ═══════════════════════════════════════════════════════════════
# 양파 (onion) 특화 피처
# ═══════════════════════════════════════════════════════════════

def add_onion_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 저장 사이클 기반 시즌 구간
    # 5월 수확 → 6~8월 신선, 9~11월 저장중기, 12~2월 저장말기, 3~4월 수확전품귀, 5월 수확기
    def _phase(ts):
        m = _month(ts)
        if 6 <= m <= 8:   return 0   # 신선 출하
        if 9 <= m <= 11:  return 1   # 저장 중기
        if m == 12 or m <= 2: return 2  # 저장 말기
        if 3 <= m <= 4:   return 3   # 수확 전 품귀
        return 4                      # 수확기 (5월)
    df["onion_season_phase"] = [_phase(ts) for ts in df.index]

    # 저장 고갈 지수: 저장말기(12~2월) → 수확전(3~4월)으로 갈수록 증가
    def _depletion(ts):
        m = _month(ts)
        if m == 12: return 0.3
        if m == 1:  return 0.5
        if m == 2:  return 0.7
        if m == 3:  return 0.9
        if m == 4:  return 1.0
        return 0.0
    df["storage_depletion_idx"] = [_depletion(ts) for ts in df.index]

    # 수확기(5월) 60일 이내 근접도 — 수확 직전 가격 하락 선행 신호
    def _harvest_prox(ts):
        m = _month(ts)
        # 5월 1일 기준
        from datetime import date
        try:
            d = ts.date() if hasattr(ts, 'date') else pd.Timestamp(ts).date()
            y = d.year if m <= 5 else d.year + 1
            harvest = date(y, 5, 1)
            days = (harvest - d).days
            return _proximity(days, 60)
        except Exception:
            return 0.0
    df["harvest_proximity_60d"] = [_harvest_prox(ts) for ts in df.index]

    # 직전 수확 후 경과 개월 (저장 압박 선형 증가)
    def _post_harvest_months(ts):
        m = _month(ts)
        # 5월 수확 기준
        if m >= 5:   return m - 5
        return m + 7   # 다음해 5월까지
    df["post_harvest_month"] = [_post_harvest_months(ts) for ts in df.index]

    # 품귀 위험도 (저장말기+수확전)
    df["storage_scarcity_risk"] = df["storage_depletion_idx"] * (
        df["onion_season_phase"].isin([2, 3]).astype(float)
    )

    # 전남 기온 이상 (주산지 날씨)
    df["south_temp_stress"] = _safe_col(df, "w_temp_dev").abs()

    return df


# ═══════════════════════════════════════════════════════════════
# 마늘 (garlic) 특화 피처
# ═══════════════════════════════════════════════════════════════

def add_garlic_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 계절 구간 (양파와 유사하나 저장 기간 더 김, 최대 10개월)
    def _phase(ts):
        m = _month(ts)
        if 6 <= m <= 8:    return 0  # 신선
        if 9 <= m <= 11:   return 1  # 저장 중기
        if m == 12 or m <= 2: return 2  # 저장 말기
        if 3 <= m <= 4:    return 3  # 수확전 품귀
        return 4                      # 수확기(5~6월)
    df["garlic_season_phase"] = [_phase(ts) for ts in df.index]

    # 의성 기온 이상 — 이 피처는 주산지가 KR-47(의성)로 설정된 경우 w_temp_dev 그대로 사용
    df["uiseong_temp_dev"] = _safe_col(df, "w_temp_dev")

    # 의성 한파 7일 누적
    df["uiseong_cold_risk"] = _safe_col(df, "w_cold_alert_7d")

    # 저장 경과월 지수 (5월 수확, 10개월 저장)
    def _storage_month(ts):
        m = _month(ts)
        if m >= 5: return m - 5
        return m + 7
    df["storage_month_idx"] = [_storage_month(ts) for ts in df.index]

    # 저장 말기 품귀 위험 (2~4월, 저장 9~11개월차)
    def _scarcity(ts):
        m = _month(ts)
        if m == 2: return 0.6
        if m == 3: return 0.85
        if m == 4: return 1.0
        return 0.0
    df["garlic_scarcity_risk"] = [_scarcity(ts) for ts in df.index]

    # 겨울 동해 위험 (12~2월 한파 누적)
    cold = _safe_col(df, "w_cold_alert_7d")
    is_winter = pd.Series(
        [1 if _month(ts) in (12, 1, 2) else 0 for ts in df.index],
        index=df.index
    )
    df["winter_cold_damage"] = cold * is_winter

    return df


# ═══════════════════════════════════════════════════════════════
# 대파 (green_onion) 특화 피처
# ═══════════════════════════════════════════════════════════════

def add_green_onion_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 계절 구간
    def _phase(ts):
        m = _month(ts)
        if 3 <= m <= 5:  return 0
        if 6 <= m <= 8:  return 1
        if 9 <= m <= 11: return 2
        return 3
    df["green_onion_season_phase"] = [_phase(ts) for ts in df.index]

    # 고온 스트레스 누적 (35℃ 이상 — heat_alert 활용)
    heat = _safe_col(df, "w_heat_alert_7d")
    df["heat_stress_acc_7d"] = heat

    # 한파 동해 위험 (-5℃ 이하 — cold_alert 활용)
    cold = _safe_col(df, "w_cold_alert_7d")
    df["cold_damage_risk_7d"] = cold

    # 집중호우 누적
    df["heavy_rain_acc_7d"] = _safe_col(df, "w_heavy_rain_7d")

    # 공급 중단 종합 점수 (0~1)
    # 폭염·한파·집중호우의 가중합, 클리핑
    df["supply_disruption_score"] = (
        heat * 0.4 + cold * 0.4 + _safe_col(df, "w_heavy_rain_7d") * 0.2
    ).clip(0, 1)

    # 기온 변동성 근사 (avg_temp의 7일 표준편차)
    temp = _safe_col(df, "w_avg_temp")
    df["temp_diurnal_range_7d"] = temp.rolling(7, min_periods=1).std().fillna(0)

    # 기상 충격 후 1주 지연 가격 반응 (ret_7d의 지연)
    ret7 = _safe_col(df, "ret_7d")
    df["weather_price_lag1"] = ret7.shift(7).fillna(0)

    return df


# ═══════════════════════════════════════════════════════════════
# 무 (radish) 특화 피처
# ═══════════════════════════════════════════════════════════════

def add_radish_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 계절 구간 (봄·여름·가을·월동)
    def _phase(ts):
        m = _month(ts)
        if 3 <= m <= 5:  return 0  # 봄무
        if 6 <= m <= 8:  return 1  # 여름무
        if 9 <= m <= 11: return 2  # 가을무
        return 3                    # 월동무(12~2)
    df["radish_season_phase"] = [_phase(ts) for ts in df.index]

    # 여름 고온 부패 위험 (7~8월 heat_alert 기반)
    heat = _safe_col(df, "w_heat_alert_7d")
    temp = _safe_col(df, "w_avg_temp")
    is_summer = pd.Series(
        [1 if _month(ts) in (7, 8) else 0 for ts in df.index],
        index=df.index
    )
    df["summer_heat_loss_risk"] = heat * is_summer

    # 월동무 안정기 (12~2월, 가격 비교적 안정)
    df["winter_radish_stable"] = pd.Series(
        [1 if _month(ts) in (12, 1, 2) else 0 for ts in df.index],
        index=df.index
    ).astype(float)

    # 김장무 연동 수요 (배추 김장과 함께 10~12월 수요 증가)
    kimjang_prox = _safe_col(df, "kimjang_proximity")
    is_kimjang = _safe_col(df, "is_kimjang_season")
    df["kimjang_radish_demand"] = kimjang_prox * 0.6 + is_kimjang * 0.4

    # 30일 누적 고온 부패 확률 (여름 고온일 누적 / 30)
    df["heat_damage_prob_30d"] = (
        heat.rolling(30, min_periods=1).sum() / 30
    ).clip(0, 1)

    # 봄무 과잉 출하 리스크 (4~5월 가격 급락 패턴)
    def _spring_glut(ts):
        m = _month(ts)
        if m == 4: return 0.7
        if m == 5: return 1.0
        return 0.0
    df["spring_radish_glut"] = [_spring_glut(ts) for ts in df.index]

    return df


# ═══════════════════════════════════════════════════════════════
# 품목 → 특화 피처 함수 라우터
# ═══════════════════════════════════════════════════════════════

ITEM_FEATURE_BUILDERS = {
    "cabbage":     add_cabbage_features,
    "onion":       add_onion_features,
    "garlic":      add_garlic_features,
    "green_onion": add_green_onion_features,
    "radish":      add_radish_features,
}


def build_item_features(df: pd.DataFrame, item_code: str) -> pd.DataFrame:
    """공통 피처 DataFrame에 품목별 특화 피처 추가"""
    builder = ITEM_FEATURE_BUILDERS.get(item_code)
    if builder is None:
        return df
    return builder(df)
