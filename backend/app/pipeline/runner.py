"""
품목별 예측 파이프라인 실행기

각 품목은 item_configs.py 의 설정대로 다른 피처·모델·파라미터를 사용.
- 배추: 14일 예측, 김장 특화 피처, 전남+강원 기상
- 양파: 21일 예측, 저장 고갈 피처, 전남+경남 기상
- 마늘: 21일 예측, 의성 한지형 기상, 품귀 피처
- 대파: 7일 단기 예측, 기상 직결 피처 최대화
- 무:  14일 예측, 여름 고온 손실 + 월동 피처
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.forecast import Forecast
from app.pipeline.features import (
    load_price_df, load_weather_df, load_market_df,
    load_production_stats, build_features,
)
from app.pipeline.features_items import build_item_features
from app.pipeline.item_configs import ITEM_ENGINE_CONFIGS, get_feature_cols
from app.pipeline.train import walk_forward_train, compute_shap


async def run_pipeline(
    item_code: str,
    base_date: date = None,
    verbose: bool = True,
) -> dict:
    """품목별 엔진으로 예측 실행 후 Forecast DB 저장"""

    cfg = ITEM_ENGINE_CONFIGS.get(item_code)
    if cfg is None:
        raise ValueError(f"지원하지 않는 품목: {item_code}")

    if base_date is None:
        base_date = date.today()

    lookback     = cfg["data_lookback_days"]
    min_rows     = cfg["min_training_rows"]
    horizon      = cfg["target_horizon"]
    primary_reg  = cfg["primary_weather_region"]
    secondary_reg = cfg.get("secondary_weather_region")
    lgbm_params  = cfg["lgbm_params"]
    feature_cols = get_feature_cols(item_code)

    start_date = base_date - timedelta(days=lookback)

    if verbose:
        print(f"\n[{cfg['name']} 엔진] {item_code} / 기준일: {base_date}")
        print(f"  학습기간: {start_date} ~ {base_date} | 예측기간: {horizon}일")
        print(f"  주산지 기상: {primary_reg} | 피처: {len(feature_cols)}개")

    async with AsyncSessionLocal() as db:
        # ── 1. 데이터 로드 ────────────────────────────────────────
        price_df   = await load_price_df(db, item_code, start_date, base_date)
        weather_df = await load_weather_df(db, primary_reg, start_date, base_date)
        market_df  = await load_market_df(db, item_code, start_date, base_date)
        prod_stats = await load_production_stats(db, item_code, base_date.year)

        # 2개 주산지 기상 병합 (있을 경우)
        if secondary_reg:
            weather_df2 = await load_weather_df(db, secondary_reg, start_date, base_date)
            if not weather_df2.empty and not weather_df.empty:
                # 두 지역 평균 (가중 없이)
                shared_idx = weather_df.index.intersection(weather_df2.index)
                if len(shared_idx) > 0:
                    num_cols = weather_df.select_dtypes("number").columns
                    weather_df.loc[shared_idx, num_cols] = (
                        weather_df.loc[shared_idx, num_cols].fillna(0) * 0.6
                        + weather_df2.loc[shared_idx, num_cols].fillna(0) * 0.4
                    )
            elif weather_df.empty and not weather_df2.empty:
                weather_df = weather_df2

        if price_df.empty:
            raise ValueError(f"가격 데이터 없음: {item_code}")

        if verbose:
            kosis_ok = "✓" if prod_stats.get("has_kosis") else "-"
            print(f"  데이터: 가격 {len(price_df)}일, 기상 {len(weather_df)}일, 거래량 {len(market_df)}일, KOSIS {kosis_ok}")

        # ── 2. 공통 피처 ──────────────────────────────────────────
        df = build_features(price_df, weather_df, prod_stats, market_df)

        # ── 3. 품목별 특화 피처 추가 ──────────────────────────────
        df = build_item_features(df, item_code)

        # 타겟 기간을 품목 설정에 맞게 재계산
        if horizon != 14:
            future_price = df["price"].shift(-horizon)
            df["target_direction"] = (future_price > df["price"] * 1.02).astype(int)
            future_max = df["price"].rolling(horizon, min_periods=1).max().shift(-horizon)
            df["target_surge"] = (future_max > df["price"] * 1.12).astype(int)
            df = df.dropna(subset=["price_ma28", "ret_14d", "target_direction"])

        # 사용 가능한 피처만 추출 (없는 컬럼은 0으로 채움)
        for col in feature_cols:
            if col not in df.columns:
                df[col] = 0.0
        df[feature_cols] = df[feature_cols].fillna(0)

        if len(df) < min_rows:
            raise ValueError(f"데이터 부족: {len(df)}행 < {min_rows}행 최소요구")

        if verbose:
            print(f"  피처 빌드 완료: {len(df)}행 × {len(feature_cols)}개")

        # ── 4. 샘플 가중치 ────────────────────────────────────────
        sample_weights = _build_sample_weights(df, cfg.get("sample_weight_fn"))

        # ── 5. Walk-Forward 학습 ──────────────────────────────────
        if verbose:
            print("  Walk-Forward 학습 중...")

        dir_model, dir_metrics = walk_forward_train(
            df, "target_direction",
            feature_cols=feature_cols,
            lgbm_params=lgbm_params,
            sample_weights=sample_weights,
        )
        surge_model, surge_metrics = walk_forward_train(
            df, "target_surge",
            feature_cols=feature_cols,
            lgbm_params=lgbm_params,
            sample_weights=sample_weights,
        )

        if verbose:
            print(f"  방향 AUC: {dir_metrics['auc']:.3f} | 급등 AUC: {surge_metrics['auc']:.3f}")

        # ── 6. 현재 시점 예측 ─────────────────────────────────────
        X_latest = df[feature_cols].dropna().tail(1)
        if X_latest.empty:
            raise ValueError("최신 피처 없음")

        up_prob   = float(dir_model.predict(X_latest)[0])
        surge_prob = float(surge_model.predict(X_latest)[0])

        direction = "up" if up_prob > 0.55 else ("down" if up_prob < 0.45 else "neutral")
        bottom_prob = 1 - up_prob

        # 변동성 위험
        recent_vol = float(df["volatility_14d"].dropna().iloc[-1]) if "volatility_14d" in df else 0.02
        vol_risk = "high" if recent_vol > 0.03 else ("medium" if recent_vol > 0.015 else "low")

        # 공급 충격 근사
        price_vs_avg = float(df["price_vs_avg_year"].dropna().iloc[-1]) if "price_vs_avg_year" in df else 0
        supply_shock = round(-price_vs_avg * 0.5, 3)

        # SHAP 상위 요인
        top_factors = compute_shap(dir_model, X_latest)

        # 신뢰도
        confidence = "high" if dir_metrics["auc"] > 0.65 else ("low" if dir_metrics["auc"] < 0.55 else "medium")

        if verbose:
            print(f"  예측: {direction} (상승확률 {up_prob:.1%}) | 급등 {surge_prob:.1%} | {confidence}")
            print(f"  요인: {[f['factor'] for f in top_factors[:3]]}")

    # ── 7. DB 저장 ────────────────────────────────────────────────
    async with AsyncSessionLocal() as save_db:
        await save_db.execute(
            delete(Forecast).where(
                Forecast.item_code == item_code,
                Forecast.base_date == base_date,
            )
        )
        save_db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version=f"lgbm_{item_code}_v2.0",
            direction_14d=direction,
            up_probability_14d=round(up_prob, 4),
            surge_probability_14d=round(surge_prob, 4),
            volatility_risk_30d=vol_risk,
            bottom_probability=round(bottom_prob, 4),
            top_factors=top_factors,
            national_supply_shock=supply_shock,
            confidence=confidence,
        ))
        await save_db.commit()

    return {
        "item_code":       item_code,
        "base_date":       str(base_date),
        "direction":       direction,
        "up_probability":  round(up_prob, 4),
        "surge_probability": round(surge_prob, 4),
        "volatility_risk": vol_risk,
        "confidence":      confidence,
        "dir_auc":         dir_metrics["auc"],
        "surge_auc":       surge_metrics["auc"],
        "feature_count":   len(feature_cols),
        "training_rows":   len(df),
        "top_factors":     [f["factor"] for f in top_factors[:3]],
    }


# ── 샘플 가중치 함수 ─────────────────────────────────────────────────────────

def _build_sample_weights(df: pd.DataFrame, weight_fn: str) -> np.ndarray | None:
    """학습 샘플 가중치 생성 — 중요 시즌 데이터 가중치 강화"""
    if weight_fn is None:
        return None

    weights = np.ones(len(df))

    months = np.array([ts.month for ts in df.index])

    if weight_fn == "kimjang_boost":
        # 김장철(10~12월) 샘플 2배 가중치
        weights[np.isin(months, [10, 11, 12])] = 2.0

    elif weight_fn == "storage_depletion_boost":
        # 저장 고갈기(1~5월) 1.8배
        weights[np.isin(months, [1, 2, 3, 4, 5])] = 1.8

    elif weight_fn == "scarcity_boost":
        # 마늘 품귀기(2~4월) 2배
        weights[np.isin(months, [2, 3, 4])] = 2.0

    elif weight_fn == "weather_shock_boost":
        # 대파: 여름(7~8월) + 겨울(12~2월) 기상 충격 시즌 1.5배
        weights[np.isin(months, [7, 8, 12, 1, 2])] = 1.5

    elif weight_fn == "summer_heat_boost":
        # 무: 여름 고온기(7~8월) 2배
        weights[np.isin(months, [7, 8])] = 2.0

    return weights
