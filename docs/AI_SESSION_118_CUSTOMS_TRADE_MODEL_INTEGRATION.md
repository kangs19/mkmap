# AI Session 118 - Customs Trade Model Integration

Date: 2026-07-07

## Goal

Connect usable customs import/export data to the crop price prediction engine and retrain horizon models with those features.

## Implemented

- Added `scripts/collect_customs_trade_features.py`
  - Downloads monthly Korea Customs Service item trade rows.
  - Writes cache files to `data/features/{YYYYMMDD}/customs_trade_{item}.json`.
  - Keeps API keys out of logs and output files.
  - Uses conservative `statKor` allowlists for mixed HS buckets.

- Updated `scripts/build_price_training_table.py`
  - Loads cached customs trade rows.
  - Adds 10 numeric model features:
    - `customs_trade_available`
    - `customs_mapping_confidence`
    - `customs_import_weight_log`
    - `customs_import_value_log`
    - `customs_import_unit_value_norm`
    - `customs_export_weight_log`
    - `customs_net_import_weight_log`
    - `customs_import_mom_change`
    - `customs_import_yoy_change`
    - `customs_import_3m_pressure`
  - Uses only the previous completed month for each training row to avoid future-data leakage.

- Updated `scripts/run_daily_model_promotion.py`
  - Adds customs trade collection before training.
  - Treats customs collection failure as non-fatal so a temporary public API issue does not stop daily model training.
  - Adds customs features to the compact 90-day feature allowlist.

## Data Collected

Ran:

```powershell
python scripts\collect_customs_trade_features.py --date 2026-07-06 --start-month 2024-01 --end-month 2026-06
```

Result:

- API collection succeeded.
- Monthly rows available mostly from 2024-01 through 2026-05.
- 16 crop cache files were generated with usable or baseline trade rows.
- `radish`, `fresh_pepper`, `perilla`, and `chamoe` were intentionally not connected as active import-pressure features because their current HS/statKor mapping is too broad or ambiguous.

Generated summary:

- `data/features/20260706/customs_trade_collection_summary.json`

## Training Table

Ran:

```powershell
python scripts\build_price_training_table.py --date 2026-07-06 --min-history 14
```

Result:

- `data/model/price_training_table_20260706.csv`
- Rows: 4,356
- Customs feature columns were present and nonzero in the expected items.

Feature coverage highlights:

- `customs_trade_available`: 3,511 nonzero rows
- `customs_import_weight_log`: 2,338 nonzero rows
- `customs_import_mom_change`: 2,407 nonzero rows
- `customs_import_yoy_change`: 2,453 nonzero rows

## Models Trained

First full candidate:

- Prefix: `price_horizon_model_20260706_customs_trade_candidate`
- Horizons trained: 1, 14, 30, 90, 180
- 365-day skipped because `target_365d_change` has 0 usable rows in the current training table.

Controlled candidate:

- Prefix: `price_horizon_model_20260706_customs_trade_controlled`
- Uses each existing baseline model's feature list plus the 10 customs features.
- Horizons trained: 1, 14, 30, 90, 180

Comparison report:

- `data/model/horizons/price_horizon_model_20260706_customs_trade_controlled_comparison.json`

## Decision

Do not promote the customs-trade candidate to production yet.

Reason: the new features are connected correctly, but the controlled candidate did not beat the current `price_horizon_model_20260706_20items_at_checked` model on rolling backtest stability. Some holdout test metrics improved for 30/90/180 days, but rolling backtest direction accuracy and MAE regressed.

Key comparison against the current checked model:

| Horizon | Decision | Main Reason |
| --- | --- | --- |
| 1d | Keep baseline | MAE improved slightly, but direction accuracy fell. |
| 14d | Keep baseline | Test and rolling backtest both regressed. |
| 30d | Keep baseline | Test direction improved, but rolling backtest regressed sharply. |
| 90d | Keep baseline | Test direction improved slightly, but backtest MAE and direction regressed. |
| 180d | Keep baseline | Test metrics improved, but rolling backtest regressed. |
| 365d | No candidate | No usable 365-day target rows. |

## Next Work

1. Keep collecting customs rows daily/monthly so the history gets longer.
2. Add country-origin features after endpoint verification:
   - dominant origin country
   - origin concentration
   - China-share for onion/garlic/carrot/pepper
3. Use customs features in item-specific models first instead of the global model.
4. Re-test only medium-term horizons after more months accumulate.
5. Do not expose customs-driven explanations in the UI until the feature passes rolling backtest gates.
