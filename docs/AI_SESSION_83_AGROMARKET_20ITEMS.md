# Session 83 - Agromarket Regional Price Check For 20 Crops (2026-07-06)

## Purpose

Continue the crop expansion work after Session 82 by attaching the newly available Agromarket regional price source to the 20-crop experimental model set.

The main question was:

- Does adding Agromarket regional price data make the 20-crop model stable enough to promote?

Short answer:

- No. Data collection succeeded, and some test metrics improved, but time-ordered backtest stability is still not strong enough for production promotion.
- Keep the public production model on the existing checked baseline until the added crops have verified production, weather, FarmMap, and market context features.

## Code Change

Updated `scripts/audit_kamis_candidate_items.py`.

- Existing metadata KAMIS mappings are now recognized even when the UI crop name does not exactly match the KAMIS codebook item name.
- This prevents already mapped crops such as `green_onion` and `garlic` from being reported as `no_mapping`.
- The audit result now returns `already_mapped` for those cases.

Reason:

- UI labels and KAMIS official item names can differ.
- Existing validated metadata should be treated as a source of truth unless a better official mapping is found.

## KAMIS Candidate Audit Recheck

Command:

```powershell
python scripts\audit_kamis_candidate_items.py --date 2026-07-06 --days-back 30 --max-variants 8 --output data\diagnostics\kamis_candidate_item_audit_20260706_v2.json
```

Result:

| Status | Count |
| --- | ---: |
| ready | 18 |
| already_mapped | 2 |
| no_mapping | 1 |
| no_recent_price | 2 |

Interpretation:

- 20 crops can be handled through either ready KAMIS matches or existing metadata mappings.
- Remaining not-added crops:
  - `zucchini`: no exact KAMIS mapping yet.
  - `grape`: mapping exists, but no recent 30-day price rows in this audit.
  - `strawberry`: mapping exists, but no recent 30-day price rows in this audit.

## Agromarket Regional Price Collection

Command:

```powershell
python scripts\collect_live_price_features.py --date 2026-07-06 --days-back 365 --services at_regional_price
```

Result:

- Collection status: all 20 crops succeeded.
- No item failed.

Feature counts:

| Item | Agromarket regional features |
| --- | ---: |
| apple | 100 |
| cabbage | 346 |
| carrot | 100 |
| chamoe | 100 |
| cucumber | 100 |
| fresh_pepper | 100 |
| garlic | 200 |
| green_onion | 100 |
| lettuce | 100 |
| onion | 100 |
| pear | 100 |
| pepper | 100 |
| perilla | 100 |
| potato | 100 |
| radish | 352 |
| sesame | 100 |
| spinach | 100 |
| sweet_potato | 100 |
| tomato | 100 |
| watermelon | 100 |

Interpretation:

- The source is reachable and usable for all 20 items.
- Counts are not evenly rich by item. Cabbage and radish have broader regional coverage; many added items have only 100 rows.
- This source helps, but by itself is not enough to prove long-horizon stability.

## Training Table Rebuild

Command:

```powershell
python scripts\build_price_training_table.py --date 2026-07-06 --min-history 14
```

Result:

- Output: `data/model/price_training_table_20260706.csv`
- Rows: 4,336
- Columns: 91

Note:

- Row count stayed the same because the table is still driven by available target price rows.
- Agromarket regional data expands feature context, not target-date coverage.

## 20-Crop Agromarket Candidate Model

Command:

```powershell
python scripts\run_daily_model_promotion.py --date 2026-07-06 --baseline-prefix price_horizon_model_20260706_all_items_checked_no365 --candidate-prefix price_horizon_model_20260706_20items_at_candidate --approved-prefix price_horizon_model_20260706_20items_at_checked --horizons 1,14,30,90,180 --backtest-window-count 40 --backtest-min-train-rows 120 --robustness-samples-per-era 3 --min-history 14 --artifact-label 20items_at --output data\model\daily_model_promotion_20260706_20items_at_checked.json
```

Result:

- Full pipeline completed.
- Candidate models trained for 1, 14, 30, 90, and 180 days.
- Prediction and explanation files were generated with the non-daily artifact label `20items_at`.
- Experimental artifacts did not overwrite the daily latest artifact names.

Generated local experimental outputs:

- `data/model/latest_price_horizon_predictions_20260706_20items_at_warn_candidates.json`
- `data/model/latest_price_horizon_predictions_20260706_20items_at_strict_candidates.json`
- `data/model/latest_price_horizon_explanations_20260706_20items_at_warn_candidates.json`
- `data/model/latest_price_horizon_explanations_20260706_20items_at_strict_candidates.json`

## Promotion Result

All horizons kept the baseline.

| Horizon | Approved source | Main reason |
| ---: | --- | --- |
| 1d | baseline | Candidate had lower direction accuracy despite slightly better MAE. |
| 14d | baseline | Candidate failed direction and MAE gates. |
| 30d | baseline | Candidate improved test direction but failed backtest direction and MAE gates. |
| 90d | baseline | Candidate failed direction and MAE gates. |
| 180d | baseline | Candidate improved test direction and test MAE but failed backtest direction and backtest MAE gates. |

Candidate versus baseline:

| Horizon | Baseline test dir | Candidate test dir | Baseline backtest dir | Candidate backtest dir | Baseline test MAE | Candidate test MAE | Baseline backtest MAE | Candidate backtest MAE |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1d | 0.8103 | 0.7857 | 0.7900 | 0.7840 | 0.022823 | 0.022469 | 0.026196 | 0.022686 |
| 14d | 0.6629 | 0.6442 | 0.8750 | 0.4623 | 0.092674 | 0.096499 | 0.085158 | 0.100620 |
| 30d | 0.6846 | 0.7079 | 0.8250 | 0.5287 | 0.123283 | 0.197419 | 0.113169 | 0.139457 |
| 90d | 0.7609 | 0.7528 | 0.8100 | 0.5026 | 0.117757 | 0.143843 | 0.097798 | 0.173372 |
| 180d | 0.8389 | 0.8782 | 0.8650 | 0.6763 | 0.128676 | 0.101755 | 0.096455 | 0.171081 |

Interpretation:

- Adding Agromarket regional price data did not fix temporal instability.
- 30d and 180d have tempting test improvements, but backtest performance is weaker.
- The promotion gate correctly prevented a public regression.

## Public Readiness Judgment

Production should not use this 20-crop Agromarket candidate yet.

Safe current posture:

- Keep the existing checked baseline for public horizons.
- Keep 20-crop outputs as experimental diagnostics only.
- Do not expose the 15 newly added crops as fully trusted public forecasts until their feature coverage is verified beyond KAMIS price history.

## Why It Is Still Weak

The 15 added crops mostly have:

- KAMIS price history: available.
- Agromarket regional price: reachable, but uneven coverage.
- KOSIS production or area mappings: not verified.
- KMA crop-weather mappings: not verified.
- FarmMap crop-region summaries: not verified.
- Crop-specific event logic: draft-level only.

That means the model can learn price momentum, but it still lacks enough verified explanatory context to make stable long-horizon predictions.

## Next Recommended Work

1. Add a readiness gate per crop and per horizon.
   - Do not let draft crops affect public model promotion until their core feature coverage is verified.
   - Keep experimental predictions available under explicit labels only.

2. Build a feature coverage score by crop.
   - Price target coverage.
   - Regional price coverage.
   - Production and cultivation area coverage.
   - Weather mapping coverage.
   - FarmMap coverage.
   - Market settlement or auction coverage.

3. Continue with KOSIS mapping discovery for the 15 added crops.
   - Production volume and cultivated area are important for explaining why price changes happen.

4. Continue with KMA crop-weather mapping verification.
   - PA_CROP_SPE_ID and AREA_ID must be official or clearly marked as unavailable.

5. Add per-item backtest reporting.
   - Current horizon-level gates can hide weak individual crops.
   - Public UX needs item-level reliability labels.

6. Train candidate models after each major feature-source addition.
   - Use a non-daily artifact label such as `20items_kosis`, `20items_kma`, or `20items_farmmap`.
   - Promote only when test and temporal backtest gates both pass.

## Verification

Commands:

```powershell
python scripts\run_smoke_suite.py --timeout-seconds 300
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q
```

Result:

- Smoke suite passed.
- Metadata validation passed: 20 items.
- External mapping validation passed: 20 items.
- API service catalog smoke passed: 17 configured services.
- Backend tests passed: 38 tests.
