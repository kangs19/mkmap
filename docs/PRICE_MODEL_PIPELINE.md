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
```

## Current Baseline

- Model: linear baseline using `change_1d` and `change_3d`
- Target: next observed price change
- 2026-06-29 run: 208 train rows, 52 test rows
- Test metrics: MAE `0.02179`, RMSE `0.052959`, direction accuracy `0.6923`

## Notes

- KAMIS garlic code `258/01` exists in the code table but returned no rows for the tested window, so `258/03` and `258/05` are the primary garlic variants.
- Generated data under `data/` is ignored by Git. Commit scripts, metadata, and docs, not raw keys or generated feature files.
