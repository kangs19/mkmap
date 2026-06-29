"""
품목별 엔진 설정 — 날씨 주산지, 모델 파라미터, 타겟 기간, 특화 피처 목록

각 품목의 가격 결정 메커니즘이 다르므로 별도 설정으로 분리.
- 배추: 김장철 수요 집중, 고랭지·남부 2개 주산지
- 양파: 저장성(6~8개월), 수확기 이후 저장 고갈 패턴
- 마늘: 저장성 높음, 의성 한지형 날씨 의존
- 대파: 저장성 없음, 기상 직결, 단기 예측 최우선
- 무  : 여름 고온 부패, 월동무 계절성, 배추와 김장 연동
"""

# ── 공통 기본 피처 (features.py → build_features() 출력) ─────────────────
BASE_FEATURE_COLS = [
    # 가격 피처 13개
    "price_ma7", "price_ma14", "price_ma28",
    "ret_1d", "ret_7d", "ret_14d",
    "volatility_7d", "volatility_14d",
    "price_vs_avg_year", "price_vs_prev_year",
    "ma7_vs_ma28",
    "sin_month", "cos_month",
    # 기상 피처 8개
    "w_avg_temp", "w_precipitation", "w_temp_dev",
    "w_temp_ma7", "w_precip_ma7",
    "w_heat_alert_7d", "w_cold_alert_7d", "w_heavy_rain_7d",
    # KOSIS 생산통계 피처 3개
    "kosis_area_dev", "kosis_prod_dev", "kosis_supply_risk",
    # 거래량 피처 5개
    "mkt_volume_kg", "mkt_volume_ma7", "mkt_volume_ma28",
    "mkt_volume_vs_avg", "mkt_volume_trend",
    # 공통 이벤트 피처 9개
    "days_to_kimjang", "is_kimjang_season", "kimjang_proximity",
    "days_to_chuseok", "chuseok_proximity",
    "days_to_seol", "seol_proximity",
    "is_school_demand", "is_summer_break",
]

# ── 품목별 특화 피처 ─────────────────────────────────────────────────────────

CABBAGE_EXTRA_FEATURES = [
    "kimjang_urgency_90d",      # 90일 이내 김장철 접근 강도 (0~1)
    "kimjang_urgency_30d",      # 30일 이내 — 급등 직전 신호
    "cabbage_season_phase",     # 0=봄출하, 1=고랭지여름, 2=가을출하, 3=겨울품귀
    "highland_temp_stress",     # 고랭지 기온 이상 (7~9월 핵심)
    "autumn_supply_pressure",   # 가을배추 출하기 공급 압박 (10~11월)
    "kimjang_vol_spike",        # 김장 시즌 전 30일 가격 변동성
    "double_region_stress",     # 전남+강원 동시 이상기온 (=공급 충격)
]

ONION_EXTRA_FEATURES = [
    "onion_season_phase",       # 0=신선(6~8), 1=저장중기(9~11), 2=저장말기(12~2), 3=수확전(3~4), 4=수확기(5)
    "storage_depletion_idx",    # 수확 후 경과월 기반 저장 고갈 지수 (3~5월 급등 패턴)
    "harvest_proximity_60d",    # 수확기(5월) 60일 이내 근접도 (0~1)
    "post_harvest_month",       # 직전 수확 후 경과 개월수
    "storage_scarcity_risk",    # 저장 말기(1~4월) 품귀 위험도 (0~1)
    "south_temp_stress",        # 전남 기온 이상 (양파 주산지)
]

GARLIC_EXTRA_FEATURES = [
    "garlic_season_phase",      # 0=신선(6~8), 1=저장중기(9~11), 2=저장말기(12~2), 3=수확전(3~4), 4=수확기(5~6)
    "uiseong_temp_dev",         # 의성(KR-47) 기온 이상 — 한지형 마늘 핵심
    "uiseong_cold_risk",        # 의성 한파 누적 7일
    "storage_month_idx",        # 수확 후 저장 경과월 (마늘: 최대 10개월)
    "garlic_scarcity_risk",     # 저장 말기(2~4월) 품귀 위험 (0~1)
    "winter_cold_damage",       # 겨울 월동 동해 위험도
]

GREEN_ONION_EXTRA_FEATURES = [
    "heat_stress_acc_7d",       # 35℃ 이상 일수 7일 누적 (고온 손실)
    "cold_damage_risk_7d",      # -5℃ 이하 한파 누적 (동해)
    "heavy_rain_acc_7d",        # 집중호우 7일 누적 횟수
    "supply_disruption_score",  # 기상 기반 공급 중단 종합 점수 (0~1)
    "temp_diurnal_range_7d",    # 7일 평균 일교차 (스트레스)
    "weather_price_lag1",       # 기상 충격 → 가격 1주 지연 반응
    "green_onion_season_phase", # 0=봄(3~5), 1=여름(6~8), 2=가을(9~11), 3=겨울(12~2)
]

RADISH_EXTRA_FEATURES = [
    "radish_season_phase",      # 0=봄무(3~5), 1=여름무(6~8), 2=가을무(9~11), 3=월동무(12~2)
    "summer_heat_loss_risk",    # 7~8월 30℃+ 고온 누적 — 부패 손실
    "winter_radish_stable",     # 12~2월 월동무 출하 안정기 (0/1)
    "kimjang_radish_demand",    # 김장무 연동 수요 (10~12월)
    "heat_damage_prob_30d",     # 30일 누적 고온 부패 확률 (0~1)
    "spring_radish_glut",       # 봄무 과잉 출하 리스크 (4~5월 가격 급락)
]

# ── 품목별 전체 설정 ─────────────────────────────────────────────────────────

ITEM_ENGINE_CONFIGS = {

    "cabbage": {
        "name": "배추",
        # 주산지 기상 (1순위: 전남해남, 2순위: 강원고랭지)
        "primary_weather_region":   "KR-46",  # 전남 — 가을배추
        "secondary_weather_region": "KR-42",  # 강원 — 여름고랭지
        # 학습 파라미터
        "data_lookback_days": 730,
        "min_training_rows":  60,
        "target_horizon":     14,    # 14일 후 방향 예측
        # LightGBM 하이퍼파라미터 — 계절성 패턴 강한 품목
        "lgbm_params": {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 5,
            "num_leaves": 31,
            "min_child_samples": 15,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
        },
        # 특화 피처
        "extra_feature_cols": CABBAGE_EXTRA_FEATURES,
        # 계절별 예측 가중치 조정 (10~12월 김장 시즌 더 보수적 학습)
        "sample_weight_fn": "kimjang_boost",  # 김장 시즌 샘플 가중치 2배
    },

    "onion": {
        "name": "양파",
        "primary_weather_region":   "KR-46",  # 전남 무안
        "secondary_weather_region": "KR-48",  # 경남 창원
        "data_lookback_days": 730,
        "min_training_rows":  60,
        "target_horizon":     21,    # 저장성 고려 — 21일 예측
        # LightGBM — 저장 고갈 패턴(비선형 급등) 포착에 깊은 트리
        "lgbm_params": {
            "n_estimators": 400,
            "learning_rate": 0.04,
            "max_depth": 6,
            "num_leaves": 50,
            "min_child_samples": 10,
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_alpha": 0.05,
            "reg_lambda": 0.2,
        },
        "extra_feature_cols": ONION_EXTRA_FEATURES,
        "sample_weight_fn": "storage_depletion_boost",  # 3~5월 고갈기 가중치
    },

    "garlic": {
        "name": "마늘",
        "primary_weather_region":   "KR-47",  # 경북 의성 (한지형)
        "secondary_weather_region": "KR-46",  # 전남 해남 (난지형)
        "data_lookback_days": 730,
        "min_training_rows":  60,
        "target_horizon":     21,    # 저장성 높음 — 21일 예측
        "lgbm_params": {
            "n_estimators": 350,
            "learning_rate": 0.045,
            "max_depth": 6,
            "num_leaves": 40,
            "min_child_samples": 12,
            "subsample": 0.8,
            "colsample_bytree": 0.75,
            "reg_alpha": 0.1,
            "reg_lambda": 0.15,
        },
        "extra_feature_cols": GARLIC_EXTRA_FEATURES,
        "sample_weight_fn": "scarcity_boost",  # 2~4월 품귀기 가중치
    },

    "green_onion": {
        "name": "대파",
        "primary_weather_region":   "KR-46",  # 전남 진도·신안
        "secondary_weather_region": "KR-41",  # 경기 (겨울 대파)
        "data_lookback_days": 540,    # 대파는 빠른 패턴 — 1.5년으로 충분
        "min_training_rows":  45,
        "target_horizon":     7,      # 저장성 없음 — 단기 7일 예측
        # LightGBM — 기상 반응 빠른 품목, 얕은 트리 + 강한 정규화
        "lgbm_params": {
            "n_estimators": 250,
            "learning_rate": 0.06,
            "max_depth": 4,
            "num_leaves": 20,
            "min_child_samples": 20,
            "subsample": 0.85,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.2,
            "reg_lambda": 0.3,
        },
        "extra_feature_cols": GREEN_ONION_EXTRA_FEATURES,
        "sample_weight_fn": "weather_shock_boost",  # 기상 충격 이후 구간 가중치
    },

    "radish": {
        "name": "무",
        "primary_weather_region":   "KR-46",  # 전남 (가을·월동)
        "secondary_weather_region": "KR-42",  # 강원 (여름고랭지)
        "data_lookback_days": 730,
        "min_training_rows":  60,
        "target_horizon":     14,
        "lgbm_params": {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "max_depth": 5,
            "num_leaves": 31,
            "min_child_samples": 15,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
        },
        "extra_feature_cols": RADISH_EXTRA_FEATURES,
        "sample_weight_fn": "summer_heat_boost",  # 여름 고온기 가중치
    },
}


def get_feature_cols(item_code: str) -> list[str]:
    """품목별 최종 피처 컬럼 리스트 반환"""
    cfg = ITEM_ENGINE_CONFIGS.get(item_code, {})
    extra = cfg.get("extra_feature_cols", [])
    return BASE_FEATURE_COLS + extra
