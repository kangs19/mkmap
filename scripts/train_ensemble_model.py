"""Multi-model ensemble trainer for price change prediction.

Trains Ridge, RandomForest, GradientBoosting, LightGBM, then averages
predictions into a weighted ensemble. Proper 3-way time split eliminates
threshold-tuning data leakage present in the baseline script.

Requires: scikit-learn, lightgbm (available in Railway Docker)
Fallback: numpy-only Ridge if sklearn unavailable

Usage:
    python scripts/train_ensemble_model.py \
        --input data/model/price_training_table_20260702.csv \
        --output data/model/price_ensemble_model_20260702.json \
        --report-output data/model/price_ensemble_model_20260702_report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date as _date
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── scikit-learn / lightgbm optional imports ──────────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[ERROR] numpy is required", file=sys.stderr)
    sys.exit(1)

try:
    from sklearn.linear_model import Ridge, Lasso
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("[WARN] scikit-learn not available — using numpy Ridge only", file=sys.stderr)

try:
    import lightgbm as lgb
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False
    print("[WARN] lightgbm not available", file=sys.stderr)

# ── constants ─────────────────────────────────────────────────────────────────
EXCLUDED = {
    "base_date", "item_code", "target_next_change",
    "avg_price", "lag_1_price", "lag_3_price", "lag_7_price", "lag_14_price",
    "ma_7_price", "ma_14_price", "ma_28_price",
}

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default=None)
    p.add_argument("--report-output", default=None)
    p.add_argument("--train-ratio", type=float, default=0.65)
    p.add_argument("--val-ratio", type=float, default=0.15)
    # test_ratio = 1 - train_ratio - val_ratio
    p.add_argument("--backtest-days", type=int, default=90,
                   help="Rolling backtest window in days (from end of data)")
    p.add_argument("--min-item-rows", type=int, default=20)
    return p.parse_args()

# ── data loading ──────────────────────────────────────────────────────────────

def load_data(path: Path) -> tuple[list[dict], list[str]]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        features = [c for c in (reader.fieldnames or []) if c not in EXCLUDED]
        for row in reader:
            try:
                parsed = {
                    "base_date": row["base_date"],
                    "item_code": row["item_code"],
                    "target": float(row["target_next_change"]),
                }
                for feat in features:
                    parsed[feat] = float(row[feat])
                rows.append(parsed)
            except (ValueError, KeyError):
                continue
    # filter constant features
    usable = [f for f in features if any(abs(r[f]) > 1e-9 for r in rows)]
    return sorted(rows, key=lambda r: (r["base_date"], r["item_code"])), usable

# ── split ─────────────────────────────────────────────────────────────────────

def three_way_split(rows: list[dict], train_r: float, val_r: float):
    n = len(rows)
    t1 = int(n * train_r)
    t2 = int(n * (train_r + val_r))
    return rows[:t1], rows[t1:t2], rows[t2:]

# ── feature matrix ────────────────────────────────────────────────────────────

def to_matrix(rows: list[dict], features: list[str]):
    X = np.array([[r[f] for f in features] for r in rows], dtype=np.float64)
    y = np.array([r["target"] for r in rows], dtype=np.float64)
    return X, y

# ── direction helpers ─────────────────────────────────────────────────────────

def direction(val: float, thresh: float) -> str:
    if val > thresh:
        return "up"
    if val < -thresh:
        return "down"
    return "stable"

def tune_threshold(preds: np.ndarray, actuals: np.ndarray) -> float:
    """Tune direction threshold on validation set only."""
    best_thresh, best_acc = 0.015, -1.0
    for t in [i / 10000 for i in range(0, 301, 5)]:
        hits = sum(
            direction(float(p), t) == direction(float(a), t)
            for p, a in zip(preds, actuals)
        )
        acc = hits / len(actuals)
        if acc > best_acc or (acc == best_acc and abs(t - 0.015) < abs(best_thresh - 0.015)):
            best_acc, best_thresh = acc, t
    return round(best_thresh, 6)

def eval_metrics(preds: np.ndarray, actuals: np.ndarray, thresh: float) -> dict:
    errors = preds - actuals
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    sign_hits = np.sign(preds) == np.sign(actuals)
    dir_hits = np.array([
        direction(float(p), thresh) == direction(float(a), thresh)
        for p, a in zip(preds, actuals)
    ])
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "sign_accuracy": round(float(np.mean(sign_hits)), 4),
        "direction_accuracy": round(float(np.mean(dir_hits)), 4),
        "n": len(preds),
    }

# ── numpy Ridge (fallback) ────────────────────────────────────────────────────

class NumpyRidge:
    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self.w: np.ndarray | None = None
        self.b: float = 0.0
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "NumpyRidge":
        self.mean_ = X.mean(axis=0)
        self.std_ = X.std(axis=0)
        self.std_[self.std_ == 0] = 1.0
        Xs = (X - self.mean_) / self.std_
        n, d = Xs.shape
        # closed-form Ridge: w = (X'X + alpha*I)^-1 X'y
        A = Xs.T @ Xs + self.alpha * np.eye(d)
        b = Xs.T @ y
        self.w = np.linalg.solve(A, b)
        self.b = float(y.mean() - (Xs.mean(axis=0) @ self.w))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self.mean_ is not None and self.w is not None
        Xs = (X - self.mean_) / self.std_
        return Xs @ self.w + self.b

    def get_coefficients(self, features: list[str]) -> dict:
        if self.w is None:
            return {}
        return {f: round(float(self.w[i]), 8) for i, f in enumerate(features)}

# ── model training ────────────────────────────────────────────────────────────

def train_all_models(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    features: list[str],
    thresh: float,
) -> dict:
    """Train all available models and return performance report."""

    results = {}
    trained = {}

    # 1. Numpy Ridge (always available)
    for alpha in [0.01, 0.1, 1.0]:
        name = f"ridge_a{alpha}"
        m = NumpyRidge(alpha=alpha)
        m.fit(X_train, y_train)
        train_p = m.predict(X_train)
        val_p = m.predict(X_val)
        test_p = m.predict(X_test)
        results[name] = {
            "train": eval_metrics(train_p, y_train, thresh),
            "val": eval_metrics(val_p, y_val, thresh),
            "test": eval_metrics(test_p, y_test, thresh),
            "overfitting_ratio": round(
                eval_metrics(test_p, y_test, thresh)["mae"] /
                max(eval_metrics(train_p, y_train, thresh)["mae"], 1e-9), 3
            ),
        }
        trained[name] = m
        print(f"  [{name}] val_mae={results[name]['val']['mae']:.5f} test_mae={results[name]['test']['mae']:.5f} overfit={results[name]['overfitting_ratio']:.2f}x")

    if HAS_SKLEARN:
        # 2. Ridge (sklearn)
        for alpha in [0.1, 1.0, 10.0]:
            name = f"sk_ridge_a{alpha}"
            scaler = StandardScaler()
            Xt = scaler.fit_transform(X_train)
            m = Ridge(alpha=alpha)
            m.fit(Xt, y_train)
            train_p = m.predict(Xt)
            val_p = m.predict(scaler.transform(X_val))
            test_p = m.predict(scaler.transform(X_test))
            results[name] = {
                "train": eval_metrics(train_p, y_train, thresh),
                "val": eval_metrics(val_p, y_val, thresh),
                "test": eval_metrics(test_p, y_test, thresh),
                "overfitting_ratio": round(
                    eval_metrics(test_p, y_test, thresh)["mae"] /
                    max(eval_metrics(train_p, y_train, thresh)["mae"], 1e-9), 3
                ),
            }
            trained[name] = (m, scaler)
            print(f"  [{name}] val_mae={results[name]['val']['mae']:.5f} test_mae={results[name]['test']['mae']:.5f} overfit={results[name]['overfitting_ratio']:.2f}x")

        # 3. Random Forest
        name = "random_forest"
        m_rf = RandomForestRegressor(
            n_estimators=100, max_depth=5, min_samples_leaf=5,
            random_state=42, n_jobs=-1
        )
        m_rf.fit(X_train, y_train)
        train_p = m_rf.predict(X_train)
        val_p = m_rf.predict(X_val)
        test_p = m_rf.predict(X_test)
        results[name] = {
            "train": eval_metrics(train_p, y_train, thresh),
            "val": eval_metrics(val_p, y_val, thresh),
            "test": eval_metrics(test_p, y_test, thresh),
            "overfitting_ratio": round(
                eval_metrics(test_p, y_test, thresh)["mae"] /
                max(eval_metrics(train_p, y_train, thresh)["mae"], 1e-9), 3
            ),
            "feature_importance": {
                features[i]: round(float(imp), 6)
                for i, imp in enumerate(m_rf.feature_importances_)
            },
        }
        trained[name] = m_rf
        print(f"  [{name}] val_mae={results[name]['val']['mae']:.5f} test_mae={results[name]['test']['mae']:.5f} overfit={results[name]['overfitting_ratio']:.2f}x")

        # 4. Gradient Boosting
        name = "gradient_boost"
        m_gb = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.05,
            subsample=0.8, min_samples_leaf=5, random_state=42
        )
        m_gb.fit(X_train, y_train)
        train_p = m_gb.predict(X_train)
        val_p = m_gb.predict(X_val)
        test_p = m_gb.predict(X_test)
        results[name] = {
            "train": eval_metrics(train_p, y_train, thresh),
            "val": eval_metrics(val_p, y_val, thresh),
            "test": eval_metrics(test_p, y_test, thresh),
            "overfitting_ratio": round(
                eval_metrics(test_p, y_test, thresh)["mae"] /
                max(eval_metrics(train_p, y_train, thresh)["mae"], 1e-9), 3
            ),
        }
        trained[name] = m_gb
        print(f"  [{name}] val_mae={results[name]['val']['mae']:.5f} test_mae={results[name]['test']['mae']:.5f} overfit={results[name]['overfitting_ratio']:.2f}x")

    if HAS_LGBM:
        # 5. LightGBM
        name = "lightgbm"
        m_lgb = lgb.LGBMRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            num_leaves=15, min_child_samples=10,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1,
            random_state=42, n_jobs=-1, verbose=-1
        )
        m_lgb.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(20, verbose=False)],
        )
        train_p = m_lgb.predict(X_train)
        val_p = m_lgb.predict(X_val)
        test_p = m_lgb.predict(X_test)
        results[name] = {
            "train": eval_metrics(train_p, y_train, thresh),
            "val": eval_metrics(val_p, y_val, thresh),
            "test": eval_metrics(test_p, y_test, thresh),
            "overfitting_ratio": round(
                eval_metrics(test_p, y_test, thresh)["mae"] /
                max(eval_metrics(train_p, y_train, thresh)["mae"], 1e-9), 3
            ),
            "feature_importance": {
                features[i]: round(float(imp), 6)
                for i, imp in enumerate(m_lgb.feature_importances_)
            },
            "best_iteration": int(m_lgb.best_iteration_),
        }
        trained[name] = m_lgb
        print(f"  [{name}] val_mae={results[name]['val']['mae']:.5f} test_mae={results[name]['test']['mae']:.5f} overfit={results[name]['overfitting_ratio']:.2f}x best_iter={m_lgb.best_iteration_}")

    return results, trained

# ── ensemble ──────────────────────────────────────────────────────────────────

def build_ensemble_predictions(
    trained: dict,
    X: np.ndarray,
    features: list[str],
) -> np.ndarray:
    """Average predictions from all trained models."""
    preds_list = []
    for name, model in trained.items():
        if isinstance(model, NumpyRidge):
            preds_list.append(model.predict(X))
        elif isinstance(model, tuple):  # (sklearn_model, scaler)
            m, scaler = model
            preds_list.append(m.predict(scaler.transform(X)))
        else:
            preds_list.append(model.predict(X))
    return np.mean(preds_list, axis=0)

# ── rolling 3-month backtest ──────────────────────────────────────────────────

def rolling_backtest_90d(
    rows: list[dict],
    features: list[str],
    backtest_days: int = 90,
    min_train: int = 100,
) -> dict:
    """
    Walk-forward backtest: for each day in the last `backtest_days` days,
    train on all prior data and predict the next day's change.
    """
    if len(rows) < min_train + backtest_days:
        return {"error": "not enough data for 90-day backtest"}

    # Collect unique dates in last backtest_days
    all_dates = sorted(set(r["base_date"] for r in rows))
    cutoff_date = all_dates[-(backtest_days + 1)]  # start of backtest window

    predictions = []
    by_item: dict[str, list] = {}

    for i, test_date in enumerate(all_dates):
        if test_date <= cutoff_date:
            continue
        train_rows = [r for r in rows if r["base_date"] < test_date]
        test_rows = [r for r in rows if r["base_date"] == test_date]
        if len(train_rows) < min_train or not test_rows:
            continue

        X_tr, y_tr = to_matrix(train_rows, features)
        X_te, y_te = to_matrix(test_rows, features)

        # Use Ridge (always available)
        m = NumpyRidge(alpha=0.1)
        m.fit(X_tr, y_tr)
        preds = m.predict(X_te)

        thresh = tune_threshold(m.predict(X_tr), y_tr)

        for j, row in enumerate(test_rows):
            pred = float(preds[j])
            actual = float(y_te[j])
            item = row["item_code"]
            entry = {
                "base_date": row["base_date"],
                "item_code": item,
                "prediction": round(pred, 6),
                "actual": round(actual, 6),
                "predicted_direction": direction(pred, thresh),
                "actual_direction": direction(actual, thresh),
                "absolute_error": round(abs(pred - actual), 6),
                "correct_direction": direction(pred, thresh) == direction(actual, thresh),
            }
            predictions.append(entry)
            by_item.setdefault(item, []).append(entry)

    if not predictions:
        return {"error": "no predictions generated"}

    all_mae = mean(p["absolute_error"] for p in predictions)
    all_dir = mean(float(p["correct_direction"]) for p in predictions)

    item_summary = {}
    for item, preds_i in by_item.items():
        item_summary[item] = {
            "mae": round(mean(p["absolute_error"] for p in preds_i), 6),
            "direction_accuracy": round(mean(float(p["correct_direction"]) for p in preds_i), 4),
            "n": len(preds_i),
        }

    return {
        "cutoff_date": cutoff_date,
        "backtest_days": backtest_days,
        "total_predictions": len(predictions),
        "overall_mae": round(all_mae, 6),
        "overall_direction_accuracy": round(all_dir, 4),
        "by_item": item_summary,
        "predictions": predictions,
    }

# ── overfitting report ────────────────────────────────────────────────────────

def overfitting_report(results: dict) -> dict:
    """Summarize overfitting risk per model."""
    report = {}
    for name, r in results.items():
        train_mae = r["train"]["mae"]
        val_mae = r["val"]["mae"]
        test_mae = r["test"]["mae"]
        ratio = test_mae / max(train_mae, 1e-9)
        risk = "high" if ratio > 2.0 else "medium" if ratio > 1.3 else "low"
        report[name] = {
            "train_mae": train_mae,
            "val_mae": val_mae,
            "test_mae": test_mae,
            "overfit_ratio": round(ratio, 3),
            "overfit_risk": risk,
            "train_dir": r["train"]["direction_accuracy"],
            "test_dir": r["test"]["direction_accuracy"],
        }
    return report

# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    print(f"[ensemble] Loading {args.input}")
    rows, features = load_data(Path(args.input))
    if len(rows) < 50:
        print(f"[ERROR] Too few rows: {len(rows)}", file=sys.stderr)
        return 1

    print(f"[ensemble] {len(rows)} rows, {len(features)} features, {len(set(r['item_code'] for r in rows))} items")
    print(f"[ensemble] Date range: {rows[0]['base_date']} → {rows[-1]['base_date']}")

    # 3-way split (by time — no shuffling)
    train, val, test = three_way_split(rows, args.train_ratio, args.val_ratio)
    print(f"[ensemble] Split: train={len(train)} val={len(val)} test={len(test)}")

    X_tr, y_tr = to_matrix(train, features)
    X_val, y_val = to_matrix(val, features)
    X_te, y_te = to_matrix(test, features)

    # Tune threshold on validation set ONLY (no leakage)
    # Use a simple ridge to get initial predictions for tuning
    ridge0 = NumpyRidge(alpha=0.1).fit(X_tr, y_tr)
    thresh = tune_threshold(ridge0.predict(X_val), y_val)
    print(f"[ensemble] Direction threshold (val-tuned): {thresh}")

    # Train all models
    print("[ensemble] Training models...")
    results, trained = train_all_models(X_tr, y_tr, X_val, y_val, X_te, y_te, features, thresh)

    # Ensemble on test
    ens_te = build_ensemble_predictions(trained, X_te, features)
    ens_val = build_ensemble_predictions(trained, X_val, features)
    results["ensemble"] = {
        "train": eval_metrics(build_ensemble_predictions(trained, X_tr, features), y_tr, thresh),
        "val": eval_metrics(ens_val, y_val, thresh),
        "test": eval_metrics(ens_te, y_te, thresh),
        "overfitting_ratio": round(
            eval_metrics(ens_te, y_te, thresh)["mae"] /
            max(eval_metrics(build_ensemble_predictions(trained, X_tr, features), y_tr, thresh)["mae"], 1e-9), 3
        ),
    }
    print(f"  [ensemble] val_mae={results['ensemble']['val']['mae']:.5f} "
          f"test_mae={results['ensemble']['test']['mae']:.5f} "
          f"overfit={results['ensemble']['overfitting_ratio']:.2f}x "
          f"test_dir={results['ensemble']['test']['direction_accuracy']*100:.1f}%")

    # 90-day rolling backtest
    print(f"\n[ensemble] Running {args.backtest_days}-day rolling backtest...")
    backtest = rolling_backtest_90d(rows, features, backtest_days=args.backtest_days)
    if "error" not in backtest:
        print(f"  Backtest: MAE={backtest['overall_mae']:.5f} "
              f"dir={backtest['overall_direction_accuracy']*100:.1f}% "
              f"n={backtest['total_predictions']}")
        print("  Per item:")
        for item, s in backtest["by_item"].items():
            print(f"    {item}: MAE={s['mae']:.5f} dir={s['direction_accuracy']*100:.1f}% n={s['n']}")

    # Overfitting summary
    overfit = overfitting_report(results)
    print("\n[ensemble] Overfitting Analysis:")
    print(f"  {'Model':<22} {'Train MAE':>10} {'Val MAE':>10} {'Test MAE':>10} {'Ratio':>6} {'Risk'}")
    for name, r in overfit.items():
        print(f"  {name:<22} {r['train_mae']:>10.5f} {r['val_mae']:>10.5f} {r['test_mae']:>10.5f} {r['overfit_ratio']:>6.2f}x {r['overfit_risk']}")

    # Best single model by val_mae
    best_name = min(
        (n for n in results if n != "ensemble"),
        key=lambda n: results[n]["val"]["mae"]
    )
    print(f"\n[ensemble] Best single model: {best_name} (val_mae={results[best_name]['val']['mae']:.5f})")
    print(f"[ensemble] Ensemble val_mae: {results['ensemble']['val']['mae']:.5f}")

    # Save report
    report_path = Path(args.report_output) if args.report_output else \
        REPO_ROOT / "data" / "model" / "price_ensemble_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_payload = {
        "run_date": str(_date.today()),
        "train_rows": len(train),
        "val_rows": len(val),
        "test_rows": len(test),
        "date_range": {"start": rows[0]["base_date"], "end": rows[-1]["base_date"]},
        "features": features,
        "direction_threshold": thresh,
        "models": results,
        "overfitting_analysis": overfit,
        "backtest_90d": {k: v for k, v in backtest.items() if k != "predictions"},
        "best_single_model": best_name,
        "ensemble_vs_best": {
            "ensemble_test_mae": results["ensemble"]["test"]["mae"],
            "best_test_mae": results[best_name]["test"]["mae"],
            "ensemble_wins": results["ensemble"]["test"]["mae"] <= results[best_name]["test"]["mae"],
        },
    }
    report_path.write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"\n[ensemble] Report saved → {report_path}")

    # Save ensemble model (Ridge coefficients for fast inference)
    best_ridge = trained.get("ridge_a0.1") or trained.get("sk_ridge_a0.1")
    if isinstance(best_ridge, NumpyRidge):
        model_payload = {
            "model_type": "ensemble_ridge_baseline",
            "features": features,
            "intercept": round(float(best_ridge.b), 10),
            "coefficients": best_ridge.get_coefficients(features),
            "feature_stats": {
                f: {"mean": float(best_ridge.mean_[i]), "std": float(best_ridge.std_[i])}
                for i, f in enumerate(features)
            },
            "direction_threshold": thresh,
            "item_models": {},
            "ensemble_report": {
                "train_rows": len(train),
                "test_rows": len(test),
                "ensemble_test_mae": results["ensemble"]["test"]["mae"],
                "ensemble_test_dir": results["ensemble"]["test"]["direction_accuracy"],
            },
            "probability_calibration": {
                "method": "backtest_mae_tanh",
                "mae": backtest.get("overall_mae", results["ensemble"]["test"]["mae"]),
                "direction_accuracy": backtest.get("overall_direction_accuracy",
                    results["ensemble"]["test"]["direction_accuracy"]),
            },
        }
        out_path = Path(args.output) if args.output else \
            REPO_ROOT / "data" / "model" / "price_ensemble_model.json"
        out_path.write_text(
            json.dumps(model_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"[ensemble] Model saved → {out_path}")

    # Save backtest predictions separately
    if "predictions" in backtest:
        bt_path = report_path.with_name(report_path.stem.replace("report", "backtest") + ".json")
        bt_path.write_text(
            json.dumps(backtest["predictions"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"[ensemble] Backtest predictions → {bt_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
