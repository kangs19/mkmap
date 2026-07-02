"""
품목별 피처 프로파일 — 각 작물 특성에 맞는 피처 가중치/선택 전략 정의.

프로파일 종류:
  A. root_storage  — 감자·무·당근·고구마 (저장성 강, 계절 단순)
  B. leafy_temp    — 배추·대파·시금치·상추·깻잎 (기온 민감, 단기 변동 큼)
  C. fruit_season  — 오이·애호박·토마토·방울토마토·수박·참외 (시설재배 중심, 여름 성수기)
  D. dried_stable  — 건고추·마늘·생강·참깨 (저장품 출하, 연간 생산량이 핵심)
  E. orchard       — 사과·배·포도 (다년생, 냉해·태풍 피해, 저장 출하 패턴)
  F. berry_season  — 딸기 (시설재배, 겨울~봄 한정)
  G. fresh_pepper  — 풋고추·붉은고추 (시설+노지 혼재, 여름 성수기)
"""

from typing import TypedDict


class FeatureProfile(TypedDict):
    profile_type: str       # 프로파일 분류
    key_season_months: list[int]   # 성수기 월 (가격 급등 구간)
    off_season_months: list[int]   # 비수기 (데이터 희소 가능)
    price_lag_focus: list[int]     # 중요 lag 피처 (일)
    rolling_focus: list[int]       # 중요 rolling window (일)
    weather_features: list[str]    # 중요 기상 피처
    has_storage_effect: bool       # 저장성 여부 → 장기 lag 중요
    has_import_competition: bool   # 수입 경쟁 여부
    kosis_important: bool          # KOSIS 생산통계 중요도
    horizon_reliability: dict      # 각 horizon 기대 신뢰도 (0~1)
    recommended_horizons: list[int] # 추천 예측 기간


ITEM_FEATURE_PROFILES: dict[str, FeatureProfile] = {

    # ─── A. 저장성 뿌리채소 ───────────────────────────────────────────────
    "potato": {
        "profile_type": "root_storage",
        "key_season_months": [6, 7, 8, 9],    # 햇감자 출하
        "off_season_months": [1, 2, 3],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.85, 14: 0.75, 21: 0.65, 28: 0.60, 60: 0.45, 90: 0.35},
        "recommended_horizons": [7, 14, 28],
    },
    "sweet_potato": {
        "profile_type": "root_storage",
        "key_season_months": [9, 10, 11],     # 수확 후 저장 출하
        "off_season_months": [5, 6, 7],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.82, 14: 0.72, 21: 0.62, 28: 0.55, 60: 0.40, 90: 0.30},
        "recommended_horizons": [7, 14, 28],
    },
    "carrot": {
        "profile_type": "root_storage",
        "key_season_months": [11, 12, 1, 2],  # 겨울당근 출하
        "off_season_months": [6, 7, 8],
        "price_lag_focus": [7, 14, 28, 60],
        "rolling_focus": [14, 30, 60],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": True,         # 수입 당근(세척) 경쟁
        "kosis_important": True,
        "horizon_reliability": {7: 0.80, 14: 0.70, 21: 0.60, 28: 0.52, 60: 0.38, 90: 0.28},
        "recommended_horizons": [7, 14, 28],
    },

    # ─── B. 엽채류 (기온 민감) ───────────────────────────────────────────
    "cabbage": {
        "profile_type": "leafy_temp",
        "key_season_months": [11, 12, 1, 2],   # 김장철
        "off_season_months": [7, 8],
        "price_lag_focus": [1, 3, 7, 14, 21],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation", "humidity"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.88, 14: 0.72, 21: 0.62, 28: 0.52, 60: 0.35, 90: 0.25},
        "recommended_horizons": [7, 14, 21],
    },
    "radish": {
        "profile_type": "leafy_temp",
        "key_season_months": [11, 12, 1],
        "off_season_months": [6, 7, 8],
        "price_lag_focus": [1, 3, 7, 14, 21],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.88, 14: 0.78, 21: 0.70, 28: 0.62, 60: 0.42, 90: 0.30},
        "recommended_horizons": [7, 14, 21, 28],
    },
    "green_onion": {
        "profile_type": "leafy_temp",
        "key_season_months": [1, 2, 3, 11, 12],
        "off_season_months": [7, 8],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.75, 14: 0.62, 21: 0.50, 28: 0.40, 60: 0.28, 90: 0.20},
        "recommended_horizons": [7, 14],
    },
    "spinach": {
        "profile_type": "leafy_temp",
        "key_season_months": [11, 12, 1, 2, 3],
        "off_season_months": [7, 8, 9],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14],
        "weather_features": ["avg_temp", "precipitation", "humidity"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.75, 14: 0.60, 21: 0.48, 28: 0.38, 60: 0.25, 90: 0.18},
        "recommended_horizons": [7, 14],
    },
    "lettuce": {
        "profile_type": "leafy_temp",
        "key_season_months": [11, 12, 1, 2, 3],  # 시설재배 겨울 성수기
        "off_season_months": [7, 8],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14],
        "weather_features": ["avg_temp", "humidity"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": False,
        "horizon_reliability": {7: 0.72, 14: 0.58, 21: 0.45, 28: 0.35, 60: 0.22, 90: 0.15},
        "recommended_horizons": [7, 14],
    },
    "perilla": {
        "profile_type": "leafy_temp",
        "key_season_months": [3, 4, 5, 6],
        "off_season_months": [12, 1],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14],
        "weather_features": ["avg_temp", "humidity"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": False,
        "horizon_reliability": {7: 0.70, 14: 0.55, 21: 0.42, 28: 0.33, 60: 0.20, 90: 0.14},
        "recommended_horizons": [7, 14],
    },

    # ─── C. 시설과채류 (여름 성수기) ─────────────────────────────────────
    "tomato": {
        "profile_type": "fruit_season",
        "key_season_months": [11, 12, 1, 2, 3, 4],  # 시설토마토 성수기
        "off_season_months": [7, 8],
        "price_lag_focus": [1, 3, 7, 14, 21],
        "rolling_focus": [7, 14, 21, 30],
        "weather_features": ["avg_temp", "humidity", "sunshine_hrs"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.80, 14: 0.68, 21: 0.58, 28: 0.48, 60: 0.33, 90: 0.22},
        "recommended_horizons": [7, 14, 21],
    },
    "cucumber": {
        "profile_type": "fruit_season",
        "key_season_months": [6, 7, 8, 9],
        "off_season_months": [12, 1, 2],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation", "humidity"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.78, 14: 0.64, 21: 0.52, 28: 0.42, 60: 0.28, 90: 0.18},
        "recommended_horizons": [7, 14, 21],
    },
    "zucchini": {
        "profile_type": "fruit_season",
        "key_season_months": [5, 6, 7, 8, 9, 10],
        "off_season_months": [12, 1, 2],
        "price_lag_focus": [1, 3, 7, 14],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.76, 14: 0.62, 21: 0.50, 28: 0.40, 60: 0.26, 90: 0.16},
        "recommended_horizons": [7, 14, 21],
    },
    "watermelon": {
        "profile_type": "fruit_season",
        "key_season_months": [5, 6, 7, 8],
        "off_season_months": [11, 12, 1, 2],
        "price_lag_focus": [7, 14, 21, 28],
        "rolling_focus": [14, 21, 28],
        "weather_features": ["avg_temp", "precipitation", "sunshine_hrs"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.75, 14: 0.60, 21: 0.48, 28: 0.38, 60: 0.22, 90: 0.14},
        "recommended_horizons": [7, 14, 21],
    },
    "chamoe": {
        "profile_type": "fruit_season",
        "key_season_months": [5, 6, 7, 8, 9],
        "off_season_months": [11, 12, 1, 2],
        "price_lag_focus": [7, 14, 21],
        "rolling_focus": [14, 21, 28],
        "weather_features": ["avg_temp", "sunshine_hrs"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.74, 14: 0.60, 21: 0.46, 28: 0.36, 60: 0.22, 90: 0.14},
        "recommended_horizons": [7, 14, 21],
    },

    # ─── D. 건조/저장 특용작물 ───────────────────────────────────────────
    "garlic": {
        "profile_type": "dried_stable",
        "key_season_months": [5, 6, 7],        # 수확 직후 가격 하락
        "off_season_months": [1, 2, 3],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": True,          # 수입 마늘
        "kosis_important": True,
        "horizon_reliability": {7: 0.85, 14: 0.75, 21: 0.68, 28: 0.60, 60: 0.45, 90: 0.32},
        "recommended_horizons": [7, 14, 21, 28],
    },
    "onion": {
        "profile_type": "dried_stable",
        "key_season_months": [5, 6, 7],
        "off_season_months": [1, 2, 3],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": True,
        "kosis_important": True,
        "horizon_reliability": {7: 0.90, 14: 0.82, 21: 0.74, 28: 0.66, 60: 0.48, 90: 0.34},
        "recommended_horizons": [7, 14, 21, 28],
    },
    "pepper": {
        "profile_type": "dried_stable",
        "key_season_months": [9, 10, 11],       # 건고추 수확 후
        "off_season_months": [3, 4, 5],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation", "sunshine_hrs"],
        "has_storage_effect": True,
        "has_import_competition": True,
        "kosis_important": True,
        "horizon_reliability": {7: 0.82, 14: 0.72, 21: 0.62, 28: 0.55, 60: 0.38, 90: 0.26},
        "recommended_horizons": [7, 14, 28],
    },
    "sesame": {
        "profile_type": "dried_stable",
        "key_season_months": [9, 10],
        "off_season_months": [1, 2, 3, 4, 5, 6],
        "price_lag_focus": [14, 28, 60, 90],
        "rolling_focus": [30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": True,
        "kosis_important": True,
        "horizon_reliability": {7: 0.70, 14: 0.62, 21: 0.55, 28: 0.48, 60: 0.36, 90: 0.26},
        "recommended_horizons": [7, 14, 28],
    },
    "fresh_pepper": {
        "profile_type": "fresh_pepper_type",
        "key_season_months": [7, 8, 9, 10],
        "off_season_months": [12, 1, 2, 3],
        "price_lag_focus": [1, 3, 7, 14, 21],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "precipitation", "sunshine_hrs"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.76, 14: 0.62, 21: 0.50, 28: 0.40, 60: 0.26, 90: 0.16},
        "recommended_horizons": [7, 14, 21],
    },

    # ─── E. 과수 (다년생, 태풍/냉해 영향) ────────────────────────────────
    "apple": {
        "profile_type": "orchard",
        "key_season_months": [9, 10, 11, 12],   # 수확 후 저장 출하
        "off_season_months": [5, 6, 7, 8],       # 햇사과 나오기 전
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.82, 14: 0.74, 21: 0.66, 28: 0.58, 60: 0.44, 90: 0.32},
        "recommended_horizons": [7, 14, 21, 28],
    },
    "pear": {
        "profile_type": "orchard",
        "key_season_months": [9, 10, 11],        # 추석 전후 수요 급증
        "off_season_months": [4, 5, 6, 7],
        "price_lag_focus": [7, 14, 28, 60, 90],
        "rolling_focus": [14, 30, 60, 90],
        "weather_features": ["avg_temp", "precipitation"],
        "has_storage_effect": True,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.82, 14: 0.74, 21: 0.66, 28: 0.58, 60: 0.44, 90: 0.32},
        "recommended_horizons": [7, 14, 21, 28],
    },
    "grape": {
        "profile_type": "orchard",
        "key_season_months": [8, 9, 10],
        "off_season_months": [1, 2, 3, 4, 5],
        "price_lag_focus": [7, 14, 28, 60],
        "rolling_focus": [14, 28, 60],
        "weather_features": ["avg_temp", "precipitation", "sunshine_hrs"],
        "has_storage_effect": True,
        "has_import_competition": True,
        "kosis_important": True,
        "horizon_reliability": {7: 0.78, 14: 0.68, 21: 0.58, 28: 0.50, 60: 0.36, 90: 0.24},
        "recommended_horizons": [7, 14, 21, 28],
    },

    # ─── F. 딸기 (시설, 겨울~봄 한정) ───────────────────────────────────
    "strawberry": {
        "profile_type": "berry_season",
        "key_season_months": [12, 1, 2, 3, 4, 5],
        "off_season_months": [7, 8, 9, 10],
        "price_lag_focus": [1, 3, 7, 14, 21],
        "rolling_focus": [7, 14, 21],
        "weather_features": ["avg_temp", "humidity", "sunshine_hrs"],
        "has_storage_effect": False,
        "has_import_competition": False,
        "kosis_important": True,
        "horizon_reliability": {7: 0.78, 14: 0.64, 21: 0.52, 28: 0.42, 60: 0.26, 90: 0.16},
        "recommended_horizons": [7, 14, 21],
    },
}


def get_profile(item_code: str) -> FeatureProfile | None:
    return ITEM_FEATURE_PROFILES.get(item_code)


def is_peak_season(item_code: str, month: int) -> bool:
    p = get_profile(item_code)
    if p is None:
        return False
    return month in p["key_season_months"]


def get_expected_horizon_reliability(item_code: str, horizon: int) -> float:
    p = get_profile(item_code)
    if p is None:
        return 0.5
    return p["horizon_reliability"].get(horizon, 0.3)
