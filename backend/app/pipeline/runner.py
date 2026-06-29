"""
예측 파이프라인 실행기
- 가격/날씨 데이터 로드
- 피처 엔지니어링
- Walk-Forward 학습
- Forecast DB 저장
"""
import asyncio
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from sqlalchemy import delete
from app.database import AsyncSessionLocal, engine, Base
from app.models.forecast import Forecast
from app.pipeline.features import (
    load_price_df, load_weather_df, load_market_df, load_production_stats,
    build_features, FEATURE_COLS
)
from app.pipeline.train import walk_forward_train, compute_shap


ITEM_CODE = "cabbage"
PRIMARY_WEATHER_REGION = "KR-42"  # 강원 (여름 고랭지 핵심 지역)
DATA_LOOKBACK_DAYS = 730  # 2년치 학습 데이터


async def run_pipeline(item_code: str = ITEM_CODE,
                       base_date: date = None,
                       verbose: bool = True) -> dict:
    if base_date is None:
        base_date = date.today()

    start_date = base_date - timedelta(days=DATA_LOOKBACK_DAYS)

    if verbose:
        print(f"\n[파이프라인 시작] {item_code} / 기준일: {base_date}")
        print(f"  학습 기간: {start_date} ~ {base_date}")

    async with AsyncSessionLocal() as db:
        # 1. 데이터 로드
        if verbose:
            print("  [1/4] 데이터 로드...")
        price_df = await load_price_df(db, item_code, start_date, base_date)
        weather_df = await load_weather_df(db, PRIMARY_WEATHER_REGION, start_date, base_date)
        market_df = await load_market_df(db, item_code, start_date, base_date)
        prod_stats = await load_production_stats(db, item_code, base_date.year)

        if price_df.empty:
            raise ValueError(f"가격 데이터 없음: {item_code} ({start_date}~{base_date})")

        if verbose:
            kosis_ok = "✓" if prod_stats.get("has_kosis") else "-"
            mkt_ok = "✓" if not market_df.empty else "-"
            print(f"    가격: {len(price_df)}일, 날씨: {len(weather_df)}일, 거래량: {len(market_df)}일, KOSIS: {kosis_ok}")

        # 2. 피처 엔지니어링
        if verbose:
            print("  [2/4] 피처 엔지니어링...")
        df = build_features(price_df, weather_df, prod_stats, market_df)

        if len(df) < 100:
            raise ValueError(f"피처 생성 후 데이터 부족: {len(df)}행")

        if verbose:
            print(f"    피처 완성: {len(df)}행 × {len(FEATURE_COLS)}개 피처")

        # 3. 모델 학습 (방향 예측 + 급등 예측)
        if verbose:
            print("  [3/4] Walk-Forward 학습...")

        dir_model, dir_metrics = walk_forward_train(df, "target_direction")
        surge_model, surge_metrics = walk_forward_train(df, "target_surge")

        if verbose:
            print(f"    방향 예측 AUC: {dir_metrics['auc']:.3f} / PR-AUC: {dir_metrics['pr_auc']:.3f}")
            print(f"    급등 예측 AUC: {surge_metrics['auc']:.3f} / PR-AUC: {surge_metrics['pr_auc']:.3f}")

        # 4. 오늘 데이터로 예측
        X_latest = df[FEATURE_COLS].dropna().tail(1)
        if X_latest.empty:
            raise ValueError("최신 피처 데이터 없음")

        up_prob = float(dir_model.predict(X_latest)[0])
        surge_prob = float(surge_model.predict(X_latest)[0])

        direction = "up" if up_prob > 0.55 else ("down" if up_prob < 0.45 else "neutral")
        bottom_prob = 1 - up_prob

        # 변동성 위험 레벨
        recent_vol = float(df["volatility_14d"].dropna().iloc[-1])
        if recent_vol > 0.03:
            vol_risk = "high"
        elif recent_vol > 0.015:
            vol_risk = "medium"
        else:
            vol_risk = "low"

        # 전국 수급 충격 (최근 14일 평균 가격 대비 편차로 근사)
        recent_price_vs_avg = float(df["price_vs_avg_year"].dropna().iloc[-1])
        supply_shock = round(-recent_price_vs_avg * 0.5, 3)  # 가격 급등 → 공급 부족 신호

        # SHAP 설명
        top_factors = compute_shap(dir_model, X_latest)

        # 신뢰도
        model_version = "lgbm_v1.0"
        confidence = "medium"
        if dir_metrics["auc"] > 0.65:
            confidence = "high"
        elif dir_metrics["auc"] < 0.55:
            confidence = "low"

        if verbose:
            print(f"\n  [예측 결과]")
            print(f"    방향: {direction} (상승확률 {up_prob:.1%})")
            print(f"    급등확률: {surge_prob:.1%}")
            print(f"    변동성: {vol_risk}")
            print(f"    신뢰도: {confidence}")
            print(f"    상위 요인: {[f['factor'] for f in top_factors[:3]]}")

        # 4. DB 저장
        if verbose:
            print("  [4/4] 예측 결과 저장...")

        async with AsyncSessionLocal() as save_db:
            # 같은 날짜 예측 덮어쓰기
            await save_db.execute(
                delete(Forecast).where(
                    Forecast.item_code == item_code,
                    Forecast.base_date == base_date,
                )
            )
            forecast = Forecast(
                item_code=item_code,
                base_date=base_date,
                model_version=model_version,
                direction_14d=direction,
                up_probability_14d=round(up_prob, 4),
                surge_probability_14d=round(surge_prob, 4),
                volatility_risk_30d=vol_risk,
                bottom_probability=round(bottom_prob, 4),
                top_factors=top_factors,
                national_supply_shock=supply_shock,
                confidence=confidence,
            )
            save_db.add(forecast)
            await save_db.commit()

        if verbose:
            print(f"  완료! Forecast ID 저장 성공")

    return {
        "item_code": item_code,
        "base_date": str(base_date),
        "direction": direction,
        "up_probability": round(up_prob, 4),
        "surge_probability": round(surge_prob, 4),
        "volatility_risk": vol_risk,
        "confidence": confidence,
        "dir_auc": dir_metrics["auc"],
        "surge_auc": surge_metrics["auc"],
    }


if __name__ == "__main__":
    result = asyncio.run(run_pipeline())
    print(f"\n결과: {result}")
