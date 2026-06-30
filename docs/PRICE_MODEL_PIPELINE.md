# Price Model Pipeline

This pipeline turns item metadata and KAMIS price history into a first-pass price-change model.

## Inputs

- `metadata/items/*.json`: item-level metadata and `external_mappings.kamis_price`
- `.env`: `KAMIS_API_KEY`; `KAMIS_CERT_ID` is optional because the connector falls back to `mkmap`
- `config/external_mappings/kamis_price_mapping.csv`: extracted KAMIS code-table mapping for the first 5 items

## Commands

```powershell
python scripts\collect_live_price_features.py --date 2026-06-29 --days-back 90
python scripts\build_price_training_table.py --date 2026-06-29
python scripts\train_price_baseline_model.py --input data\model\price_training_table_20260629.csv --output data\model\price_baseline_model_20260629.json
python scripts\predict_latest_prices.py --features data\model\price_training_table_20260629.csv --model data\model\price_baseline_model_20260629.json --output data\model\latest_price_predictions_20260629.json
python scripts\predict_latest_prices.py --features data\model\price_training_table_20260629.csv --model data\model\price_baseline_model_20260629.json --signals data\signals\20260629\region_risk_signals.json --output data\model\latest_price_predictions_20260629.json
```

## Current Baseline

- Model: standardized linear baseline using lag, trend, moving-average gap, volatility, weekday, and month features.
- Target: next observed price change.
- Prediction output can include an optional risk overlay from `region_risk_signals.json`; this keeps the pure price-history prediction and a separate `risk_adjusted_next_change`.
- The training script reads usable feature columns from the CSV, so adding new engineered columns in `build_price_training_table.py` automatically makes them available to the model.
- 2026-06-30 cached run: 120 train rows, 30 test rows, 20 features.
- Test metrics: MAE `0.017679`, RMSE `0.021859`, direction accuracy `0.5333`.

## Feature Columns

The current training table includes:

- Price level and lags: `avg_price`, `lag_1_price`, `lag_3_price`, `lag_7_price`, `lag_14_price`
- Moving averages: `ma_7_price`, `ma_14_price`, `ma_28_price`
- Momentum: `change_1d`, `change_3d`, `change_7d`, `change_14d`
- Mean reversion: `ma_7_gap`, `ma_14_gap`
- Recent volatility: `volatility_7d`, `volatility_14d`
- Calendar seasonality: `weekday_sin`, `weekday_cos`, `month_sin`, `month_cos`

## Notes

- KAMIS garlic code `258/01` exists in the code table but returned no rows for the tested window, so `258/03` and `258/05` are the primary garlic variants.
- Generated data under `data/` is ignored by Git. Commit scripts, metadata, and docs, not raw keys or generated feature files.
