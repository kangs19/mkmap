"""
LightGBM Walk-Forward 학습 + SHAP 분석
품목별 피처 컬럼·파라미터·샘플 가중치를 외부에서 주입받는 구조.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, average_precision_score
from typing import Optional

from app.pipeline.features import FEATURE_COLS as BASE_FEATURE_COLS


def walk_forward_train(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: Optional[list] = None,
    n_splits: int = 4,
    test_days: int = 60,
    lgbm_params: Optional[dict] = None,
    sample_weights: Optional[np.ndarray] = None,
) -> tuple[lgb.Booster, dict]:
    """
    Walk-Forward Validation
    - feature_cols: 품목별 피처 목록 (None이면 공통 BASE_FEATURE_COLS)
    - lgbm_params: 품목별 하이퍼파라미터 (None이면 기본값)
    - sample_weights: 샘플 가중치 배열 (None이면 균등)
    """
    if feature_cols is None:
        feature_cols = BASE_FEATURE_COLS

    # 사용 가능한 피처만 필터
    available = [c for c in feature_cols if c in df.columns]
    df_clean = df[available + [target_col]].dropna()
    n = len(df_clean)

    # 기본 LightGBM 파라미터
    base_params = {
        "objective": "binary",
        "metric": ["binary_logloss", "auc"],
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "random_state": 42,
    }
    if lgbm_params:
        # n_estimators는 lgb.train의 num_boost_round로 별도 처리
        base_params.update({k: v for k, v in lgbm_params.items() if k != "n_estimators"})
    num_boost_round = lgbm_params.get("n_estimators", 500) if lgbm_params else 500

    metrics_list = []
    model = None
    fold_size = (n - test_days) // max(n_splits, 1)

    for fold in range(n_splits):
        train_end  = fold_size * (fold + 1) + test_days
        test_start = train_end - test_days

        if test_start >= n or train_end > n:
            break

        train_df = df_clean.iloc[:test_start]
        test_df  = df_clean.iloc[test_start:train_end]

        if len(train_df) < 40 or len(test_df) < 10:
            continue

        X_train = train_df[available]
        y_train = train_df[target_col]
        X_test  = test_df[available]
        y_test  = test_df[target_col]

        # 클래스 불균형 보정
        pos_ratio = max(float(y_train.mean()), 0.01)
        scale_pos = (1 - pos_ratio) / pos_ratio
        params = {**base_params, "scale_pos_weight": scale_pos}

        # 샘플 가중치 슬라이싱
        sw_train = None
        if sample_weights is not None and len(sample_weights) == len(df_clean):
            sw_train = sample_weights[:test_start]

        train_data = lgb.Dataset(X_train, label=y_train, weight=sw_train)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

        callbacks = [lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)]
        model = lgb.train(
            params,
            train_data,
            num_boost_round=num_boost_round,
            valid_sets=[valid_data],
            callbacks=callbacks,
        )

        y_pred = model.predict(X_test)
        try:
            auc    = roc_auc_score(y_test, y_pred)
            pr_auc = average_precision_score(y_test, y_pred)
        except Exception:
            auc, pr_auc = 0.5, pos_ratio

        metrics_list.append({"fold": fold, "auc": auc, "pr_auc": pr_auc,
                              "n_train": len(train_df), "n_test": len(test_df)})

    avg_metrics = {
        "auc":    float(np.mean([m["auc"]    for m in metrics_list])) if metrics_list else 0.5,
        "pr_auc": float(np.mean([m["pr_auc"] for m in metrics_list])) if metrics_list else 0.0,
        "folds":  metrics_list,
        "feature_count": len(available),
    }

    return model, avg_metrics


def compute_shap(
    model: lgb.Booster,
    X: pd.DataFrame,
    top_n: int = 5,
) -> list[dict]:
    """LightGBM feature importance 기반 상위 기여 피처 반환"""
    if X.empty or model is None:
        return []

    importances = model.feature_importance(importance_type="gain")
    feature_names = model.feature_name()
    last_pred = float(model.predict(X.tail(1))[0])
    pred_direction = "up" if last_pred > 0.5 else "down"

    total = max(float(importances.sum()), 1e-10)
    result = []
    for feat, imp in zip(feature_names, importances):
        contrib = float(imp) / total
        result.append({
            "factor":     feat,
            "importance": round(contrib, 4),
            "direction":  pred_direction,
        })

    result.sort(key=lambda x: x["importance"], reverse=True)
    return result[:top_n]
