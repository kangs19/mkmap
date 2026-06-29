"""
LightGBM Walk-Forward 학습 + SHAP 분석
배추 가격 14일 방향 예측 / 급등 확률 예측
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score

from app.pipeline.features import FEATURE_COLS


def walk_forward_train(df: pd.DataFrame, target_col: str,
                       n_splits: int = 4, test_days: int = 60) -> tuple[lgb.Booster, dict]:
    """
    Walk-Forward Validation
    - 전체 기간을 n_splits 폴드로 분할
    - 각 폴드: 과거 데이터로 학습, 이후 test_days로 검증
    - 마지막 폴드 모델을 최종 모델로 반환
    """
    df_clean = df[FEATURE_COLS + [target_col]].dropna()
    n = len(df_clean)

    metrics_list = []
    model = None

    fold_size = (n - test_days) // n_splits

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1) + test_days
        test_start = train_end - test_days

        if test_start >= n or train_end > n:
            break

        train_df = df_clean.iloc[:test_start]
        test_df = df_clean.iloc[test_start:train_end]

        if len(train_df) < 60 or len(test_df) < 10:
            continue

        X_train = train_df[FEATURE_COLS]
        y_train = train_df[target_col]
        X_test = test_df[FEATURE_COLS]
        y_test = test_df[target_col]

        pos_ratio = y_train.mean()
        scale_pos_weight = (1 - pos_ratio) / max(pos_ratio, 0.01)

        params = {
            "objective": "binary",
            "metric": ["binary_logloss", "auc"],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 20,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "scale_pos_weight": scale_pos_weight,
            "verbose": -1,
            "random_state": 42,
        }

        train_data = lgb.Dataset(X_train, label=y_train)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

        callbacks = [lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)]
        model = lgb.train(
            params,
            train_data,
            num_boost_round=500,
            valid_sets=[valid_data],
            callbacks=callbacks,
        )

        y_pred = model.predict(X_test)
        try:
            auc = roc_auc_score(y_test, y_pred)
            pr_auc = average_precision_score(y_test, y_pred)
        except Exception:
            auc, pr_auc = 0.5, pos_ratio

        metrics_list.append({"fold": fold, "auc": auc, "pr_auc": pr_auc,
                              "n_train": len(train_df), "n_test": len(test_df)})

    avg_metrics = {
        "auc": float(np.mean([m["auc"] for m in metrics_list])) if metrics_list else 0.5,
        "pr_auc": float(np.mean([m["pr_auc"] for m in metrics_list])) if metrics_list else 0.0,
        "folds": metrics_list,
    }

    return model, avg_metrics


def compute_shap(model: lgb.Booster, X: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """LightGBM feature importance 기반 상위 기여 피처 반환
    영문 피처명 원본을 factor에 유지 → explain.py에서 한국어 변환
    """
    if X.empty:
        return []

    importances = model.feature_importance(importance_type="gain")
    last_pred = float(model.predict(X.tail(1))[0])
    pred_direction = "up" if last_pred > 0.5 else "down"

    feature_importance = []
    total = max(importances.sum(), 1e-10)
    for i, feat in enumerate(FEATURE_COLS):
        if i >= len(importances):
            break
        contrib = float(importances[i]) / total
        feature_importance.append({
            "factor": feat,           # 영문 원본 유지 (explain.py가 매핑)
            "importance": round(contrib, 4),
            "direction": pred_direction,
        })

    feature_importance.sort(key=lambda x: x["importance"], reverse=True)
    return feature_importance[:top_n]


def _compute_shap_legacy(model: lgb.Booster, X: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """구버전 호환용 — 사용 안 함"""
    importances = model.feature_importance(importance_type="gain")
    last_pred = float(model.predict(X.tail(1))[0])

    feature_importance = []
    total = max(importances.sum(), 1e-10)
    for i, feat in enumerate(FEATURE_COLS):
        contrib = float(importances[i]) / total
        feature_importance.append({
            "factor": feat,
            "contribution": round(contrib, 4),
            "direction": "up" if last_pred > 0.5 else "down",
        })

    feature_importance.sort(key=lambda x: x["contribution"], reverse=True)

    name_map = {
        "price_ma7": "7일 이동평균가격",
        "price_ma14": "14일 이동평균가격",
        "price_ma28": "28일 이동평균가격",
        "ret_1d": "전일 대비 등락률",
        "ret_7d": "7일 누적 등락률",
        "ret_14d": "14일 누적 등락률",
        "volatility_7d": "7일 변동성",
        "volatility_14d": "14일 변동성",
        "price_vs_avg_year": "평년 대비 가격 편차",
        "price_vs_prev_year": "전년 동기 대비 편차",
        "ma7_vs_ma28": "단기/장기 이동평균 크로스",
        "sin_month": "계절성 (사인)",
        "cos_month": "계절성 (코사인)",
        "w_avg_temp": "기온",
        "w_precipitation": "강수량",
        "w_temp_dev": "기온 평년 편차",
        "w_temp_ma7": "7일 평균기온",
        "w_precip_ma7": "7일 누적 강수량",
        "w_heat_alert_7d": "폭염 경보 (7일 내)",
        "w_cold_alert_7d": "한파 경보 (7일 내)",
        "w_heavy_rain_7d": "호우 경보 (7일 내)",
    }
    for f in feature_importance:
        f["factor"] = name_map.get(f["factor"], f["factor"])

    return feature_importance[:top_n]

