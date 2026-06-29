"""
파이프라인 Unit Test — 기획서 20번
피처 생성, 이벤트 엔진, 자연어 설명 모듈 검증
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date

from app.pipeline.events import compute_event_features, add_event_features, EVENT_FEATURE_COLS
from app.pipeline.explain import build_summary_text, factors_to_display, FEATURE_LABELS
from app.pipeline.features import build_features, FEATURE_COLS


# ── 이벤트 엔진 테스트 ──────────────────────────────────────────
class TestEventEngine:
    def test_kimjang_season_november(self):
        """11월은 김장 성수기"""
        feat = compute_event_features(date(2026, 11, 15))
        assert feat["is_kimjang_season"] == 1
        assert feat["kimjang_proximity"] > 0

    def test_kimjang_off_season(self):
        """3월은 김장 비시즌"""
        feat = compute_event_features(date(2026, 3, 1))
        assert feat["is_kimjang_season"] == 0

    def test_school_demand_march(self):
        """3월은 급식 수요 증가"""
        feat = compute_event_features(date(2026, 3, 5))
        assert feat["is_school_demand"] == 1

    def test_summer_break(self):
        """8월은 여름방학 급식 중단"""
        feat = compute_event_features(date(2026, 8, 1))
        assert feat["is_summer_break"] == 1

    def test_chuseok_2024_proximity(self):
        """2024 추석(9/17) 7일 전은 근접도 양수"""
        feat = compute_event_features(date(2024, 9, 10))
        assert feat["days_to_chuseok"] > 0
        assert feat["chuseok_proximity"] > 0

    def test_all_features_present(self):
        """EVENT_FEATURE_COLS 전부 반환되는지"""
        feat = compute_event_features(date(2026, 6, 29))
        for col in EVENT_FEATURE_COLS:
            assert col in feat, f"누락: {col}"

    def test_add_event_features_dataframe(self):
        """DataFrame에 이벤트 피처 추가"""
        idx = pd.date_range("2026-01-01", periods=30, freq="D")
        df = pd.DataFrame({"price": np.random.rand(30) * 5000 + 4000}, index=idx)
        result = add_event_features(df)
        for col in EVENT_FEATURE_COLS:
            assert col in result.columns


# ── 자연어 설명 테스트 ──────────────────────────────────────────
class TestExplainEngine:
    def test_build_summary_up(self):
        summary = build_summary_text("cabbage", "up", 0.65, [], "medium")
        assert "배추" in summary
        assert "상승" in summary

    def test_build_summary_with_factors(self):
        factors = [
            {"factor": "kimjang_proximity", "importance": 0.12, "direction": "up"},
            {"factor": "w_heat_alert_7d",   "importance": 0.08, "direction": "up"},
        ]
        summary = build_summary_text("cabbage", "up", 0.7, factors, "high")
        assert "김장철" in summary or "주요 요인" in summary

    def test_factors_to_display(self):
        factors = [
            {"factor": "days_to_kimjang", "importance": 0.15, "direction": "up"},
            {"factor": "price_vs_avg_year", "importance": 0.10, "direction": "up"},
        ]
        result = factors_to_display(factors)
        assert len(result) == 2
        assert "label" in result[0]
        assert "message" in result[0]

    def test_all_feature_labels_defined(self):
        """FEATURE_COLS의 모든 피처가 FEATURE_LABELS에 있는지"""
        missing = [f for f in FEATURE_COLS if f not in FEATURE_LABELS]
        assert missing == [], f"FEATURE_LABELS에 없는 피처: {missing}"


# ── 피처 파이프라인 테스트 ──────────────────────────────────────
class TestFeaturePipeline:
    def _make_price_df(self, n=200):
        idx = pd.date_range("2024-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "price": np.random.rand(n) * 3000 + 4000,
            "avg_year_price": np.random.rand(n) * 500 + 4500,
            "prev_year_price": np.random.rand(n) * 500 + 4200,
        }, index=idx)

    def test_build_features_basic(self):
        df = build_features(self._make_price_df())
        for col in FEATURE_COLS:
            assert col in df.columns, f"피처 누락: {col}"

    def test_build_features_with_weather(self):
        price_df = self._make_price_df()
        weather_df = pd.DataFrame({
            "avg_temp": np.random.rand(200) * 20 + 10,
            "precipitation": np.random.rand(200) * 5,
            "heat_alert": np.zeros(200),
            "cold_alert": np.zeros(200),
            "heavy_rain_alert": np.zeros(200),
            "temp_dev": np.random.rand(200) * 3 - 1.5,
        }, index=price_df.index)
        df = build_features(price_df, weather_df)
        assert "w_avg_temp" in df.columns
        assert "w_precip_ma7" in df.columns

    def test_event_features_in_output(self):
        df = build_features(self._make_price_df())
        assert "days_to_kimjang" in df.columns
        assert "is_kimjang_season" in df.columns

    def test_target_columns_present(self):
        df = build_features(self._make_price_df())
        assert "target_direction" in df.columns
        assert "target_surge" in df.columns
        assert df["target_direction"].isin([0, 1]).all()
