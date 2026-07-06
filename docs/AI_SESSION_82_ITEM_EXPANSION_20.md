# Session 82 - Candidate Item Expansion To 20 Crops (2026-07-06)

## Purpose

The user asked to continue from the 5-crop model work and proceed toward downloading data, selecting features, training, and backtesting for other crops.

This session expanded the metadata registry from 5 model-ready items to 20 item metadata entries, then collected KAMIS price data and trained/backtested a 20-item candidate model set.

## Added Tooling

Added `scripts/audit_kamis_candidate_items.py`.

- Reads UI item names from `index.html`.
- Parses the KAMIS codebook file at `config/external_mappings/kamis_item_codes_download` directly from XLSX XML, so no new dependency such as `openpyxl` is required.
- Calls the KAMIS API only for summary counts.
- Does not persist raw API payloads because KAMIS responses can include request condition fields containing the API key.
- Writes summary-only diagnostics to `data/diagnostics/kamis_candidate_item_audit_<date>.json`.

Added `scripts/generate_candidate_item_metadata.py`.

- Reads the KAMIS candidate audit.
- Generates draft metadata JSON files for ready, unmapped items.
- Marks generated items as `manual_review_required: true`.
- Sets KMA crop-weather mapping to `candidate_regions_only` until official PA_CROP_SPE_ID and AREA_ID mappings are verified.
- Sets KOSIS production coverage to `false` for generated items until production table mappings are verified.

Updated `scripts/audit_prediction_feature_coverage.py`.

- Default item list now comes from `default_registry().all_items()` instead of a hard-coded 5-item list.

Updated `scripts/run_daily_model_promotion.py`.

- Added `--artifact-label`.
- Default remains `daily` for existing automation compatibility.
- Experiments should pass a non-daily label such as `--artifact-label 20items` so experimental prediction files do not overwrite daily latest artifacts.

## KAMIS Candidate Audit

Command:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts\audit_kamis_candidate_items.py --date 2026-07-06 --days-back 30 --max-variants 8
```

Result:

- UI items audited: 23
- `ready`: 18
- `no_mapping`: 3
- `no_recent_price`: 2

Ready but previously unmapped items:

- potato / 감자
- sweet_potato / 고구마
- pepper / 건고추
- fresh_pepper / 풋고추
- tomato / 토마토
- cucumber / 오이
- carrot / 당근
- spinach / 시금치
- lettuce / 상추
- perilla / 깻잎
- watermelon / 수박
- chamoe / 참외
- sesame / 참깨
- apple / 사과
- pear / 배

Not added in this session:

- zucchini / 애호박: exact KAMIS item-name mapping was not found.
- grape / 포도: code exists, but no recent 30-day KAMIS price rows were returned.
- strawberry / 딸기: code exists, but no recent 30-day KAMIS price rows were returned.

Note:

- green_onion and garlic were already mapped, but the audit script does exact UI item-name matching. Existing metadata uses valid KAMIS mappings whose KAMIS names differ from the UI labels.

## Metadata Expansion

Generated 15 new metadata files:

- `metadata/items/apple.json`
- `metadata/items/carrot.json`
- `metadata/items/chamoe.json`
- `metadata/items/cucumber.json`
- `metadata/items/fresh_pepper.json`
- `metadata/items/lettuce.json`
- `metadata/items/pear.json`
- `metadata/items/pepper.json`
- `metadata/items/perilla.json`
- `metadata/items/potato.json`
- `metadata/items/sesame.json`
- `metadata/items/spinach.json`
- `metadata/items/sweet_potato.json`
- `metadata/items/tomato.json`
- `metadata/items/watermelon.json`

Validation:

```powershell
python scripts\validate_metadata.py
python scripts\validate_external_mappings.py
```

Result:

- Metadata validation passed: 20 items
- External mapping validation passed: 20 items

## Data Collection

Command:

```powershell
python scripts\collect_live_price_features.py --date 2026-07-06 --days-back 365 --services kamis_price
```

Result:

- All 20 items succeeded.
- No API errors.
- KAMIS feature counts:
  - apple: 2,738
  - cabbage: 3,572
  - carrot: 3,402
  - chamoe: 1,696
  - cucumber: 1,944
  - fresh_pepper: 2,956
  - garlic: 4,756
  - green_onion: 3,402
  - lettuce: 3,402
  - onion: 3,382
  - pear: 3,076
  - pepper: 3,376
  - perilla: 3,402
  - potato: 3,142
  - radish: 3,712
  - sesame: 3,402
  - spinach: 3,402
  - sweet_potato: 3,402
  - tomato: 3,402
  - watermelon: 3,398

## Training Table

Command:

```powershell
python scripts\build_price_training_table.py --date 2026-07-06 --min-history 14
```

Result:

- `data/model/price_training_table_20260706.csv`
- 4,336 rows
- 91 columns

Rows by item:

| Item | Rows |
| --- | ---: |
| apple | 182 |
| cabbage | 228 |
| carrot | 228 |
| chamoe | 109 |
| cucumber | 228 |
| fresh_pepper | 228 |
| garlic | 209 |
| green_onion | 228 |
| lettuce | 228 |
| onion | 228 |
| pear | 205 |
| pepper | 228 |
| perilla | 228 |
| potato | 211 |
| radish | 228 |
| sesame | 228 |
| spinach | 228 |
| sweet_potato | 228 |
| tomato | 228 |
| watermelon | 228 |

## 20-Item Candidate Model Backtest

Command:

```powershell
python scripts\run_daily_model_promotion.py --date 2026-07-06 --baseline-prefix price_horizon_model_20260706_all_items_checked_no365 --candidate-prefix price_horizon_model_20260706_20items_candidate --approved-prefix price_horizon_model_20260706_20items_checked --horizons 1,14,30,90,180 --backtest-window-count 40 --backtest-min-train-rows 120 --robustness-samples-per-era 5 --min-history 14 --output data\model\daily_model_promotion_20260706_20items_checked.json
```

Result:

- Training completed for 1, 14, 30, 90, and 180 day horizons.
- Robustness completed after the original shell timeout; the parent process finished successfully.
- Prediction/explanation artifacts were generated.

Promotion result:

| Horizon | Approved Source | Candidate Outcome |
| ---: | --- | --- |
| 1d | baseline | candidate had slightly lower direction accuracy, although MAE improved |
| 14d | baseline | candidate failed direction and MAE gates |
| 30d | baseline | candidate failed direction and MAE gates |
| 90d | baseline | candidate failed direction and MAE gates |
| 180d | baseline | candidate improved test MAE but failed backtest direction/MAE gates |

Candidate versus baseline:

| Horizon | Baseline Test Dir | Candidate Test Dir | Baseline Backtest Dir | Candidate Backtest Dir |
| ---: | ---: | ---: | ---: | ---: |
| 1d | 0.8103 | 0.7880 | 0.7900 | 0.7853 |
| 14d | 0.6629 | 0.6166 | 0.8750 | 0.4585 |
| 30d | 0.6846 | 0.6505 | 0.8250 | 0.5275 |
| 90d | 0.7609 | 0.7528 | 0.8100 | 0.5026 |
| 180d | 0.8389 | 0.8782 | 0.8650 | 0.6763 |

Strict quality result:

- 1/14/30/90 day horizons were held because of `temporal_high_risk`.
- 180 day produced predictions, but public backend policy still hides horizons above 90 days.

Interpretation:

- The 20-item model is useful as an experiment and data-readiness proof.
- It is not ready for public production use yet.
- The correct production behavior remains the existing 5-item checked champion for public horizons.

## Why The 20-Item Model Is Not Ready Yet

The 15 new items currently have:

- KAMIS price data: yes
- KMA crop-weather official mappings: not yet verified
- KOSIS production mappings: not yet verified
- FarmMap crop-region summaries: not yet verified
- Agromarket regional/settlement coverage: not yet fully collected and validated

This means the model has enough price history to learn basic price movement, but not enough verified crop-specific weather/production/regional context to justify public prediction confidence.

## Verification

Commands:

```powershell
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q
python scripts\run_smoke_suite.py --timeout-seconds 300
```

Result:

- 38 tests passed
- Smoke suite passed

## Next Work

1. Add KAMIS alias support to candidate audit so existing `green_onion` and `garlic` are recognized by their KAMIS item names.
2. Collect and validate Agromarket regional prices for the 15 new items.
3. Discover/verify KOSIS production mappings for the 15 new items.
4. Verify KMA crop-weather PA_CROP_SPE_ID and AREA_ID mappings for the 15 new items.
5. Build FarmMap crop-region summaries for the new items, or explicitly mark FarmMap as unavailable per item.
6. Re-run the 20-item model after those context features exist.
7. Use `--artifact-label 20items` for future experimental model runs so experimental outputs do not overwrite daily latest files.

## Current Readiness Judgment

- Metadata expansion: complete as draft.
- KAMIS price data: complete for 20 items.
- Model training/backtest: complete.
- Public deployment: not approved for the 15 new items yet.
- Safe public state: keep 5-item public champion active while continuing data/context enrichment for the added 15 items.
