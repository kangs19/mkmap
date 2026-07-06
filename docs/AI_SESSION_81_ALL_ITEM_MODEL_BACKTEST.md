# Session 81 - All Mapped Item Model Refresh And Backtest (2026-07-06)

## Purpose

The user asked to download data for the other crops, select crop-specific features, train models per crop, run the same backtests, and check whether the result can be applied immediately.

This session processed every crop that is currently model-ready in the repository. As of this session, the fully mapped item set is:

- `cabbage` / 배추
- `radish` / 무
- `onion` / 양파
- `green_onion` / 대파
- `garlic` / 마늘

Other crops shown in the UI are not yet safe to train because they do not yet have the required item metadata and external API code mappings under `metadata/items` and `config/external_mappings`.

## Data Collection

Environment check:

- `DATA_GO_KR_API_KEY`: configured
- `KAMIS_API_KEY`: configured
- `KAMIS_CERT_ID`: configured
- `KOSIS_API_KEY`: configured
- `KOSIS_PRODUCTION_TBL_ID`: missing, but cached KOSIS production data exists for the 5 mapped crops

Commands run:

```powershell
python scripts\check_env_status.py
python scripts\collect_live_price_features.py --date 2026-07-06 --days-back 730 --items cabbage radish onion green_onion garlic --services kamis_price
python scripts\collect_live_price_features.py --date 2026-07-06 --days-back 365 --items cabbage radish onion green_onion garlic --services at_regional_price
python scripts\audit_prediction_feature_coverage.py --start 2024-07-06 --end 2026-07-06 --items cabbage radish onion green_onion garlic --output data\diagnostics\prediction_feature_coverage_20260706.json
```

KAMIS 730-day collection counts:

| Item | Rows |
| --- | ---: |
| cabbage | 3,572 |
| radish | 3,712 |
| onion | 3,382 |
| green_onion | 3,402 |
| garlic | 4,756 |

AT regional 365-day collection counts:

| Item | Rows |
| --- | ---: |
| cabbage | 346 |
| radish | 352 |
| onion | 100 |
| green_onion | 100 |
| garlic | 200 |

AT market settlement collection was attempted, but the public API timed out before the full 5-item run completed. Partial raw files exist locally for `green_onion`, `onion`, and `radish`; `cabbage` and `garlic` returned empty/partial files in this attempt. Do not treat settlement coverage as complete yet.

## Feature Coverage

Coverage audit result:

- `price_target`: usable, 474 unique dates, 474 minimum item dates
- `price_market`: usable, 623 unique dates, 620 minimum item dates
- `agri_weather`: usable if backfilled, 372 unique dates, 326 minimum item dates
- `disaster_event`: recent/context only, 28 unique dates, 0 minimum item dates
- `forecast_context`: recent/context only, 5 unique dates, 0 minimum item dates
- `production_region`: static annual usable, 5 item records

Interpretation:

- Price data is strong enough for short and medium horizon modeling.
- Weather can be used, but it is thinner than price data and needs careful backfill handling.
- Disaster and forecast signals should be used as context/risk explanation rather than full historical training drivers until more history is collected.
- Static production/FarmMap/region features are useful, but should not dominate the model without region/date aligned volume data.

## Crop-Specific Feature Engine

The generated training table is:

- `data/model/price_training_table_20260706.csv`
- 1,121 rows
- 91 columns

Rows by item:

| Item | Rows |
| --- | ---: |
| cabbage | 228 |
| radish | 228 |
| onion | 228 |
| green_onion | 228 |
| garlic | 209 |

Common feature groups:

- KAMIS and Agromarket price levels
- wholesale/retail/settlement/volume normalized features
- weather temperature/rainfall/humidity/sunshine/observation features
- disaster/weather-alert insurance risk
- FarmMap capacity and land-use match features
- production region static annual features

Crop-specific feature examples:

- cabbage: kimjang urgency, highland temperature stress, autumn supply pressure, spring supply pressure, early autumn correction
- radish: kimjang demand, summer heat loss risk, winter phase, spring glut, summer glut pressure
- onion: storage depletion, harvest proximity, storage scarcity, post-harvest supply pressure, autumn storage transition
- garlic: storage month, scarcity risk, winter cold damage, harvest/post-harvest pressure
- green onion: heat stress, cold damage, heavy rain, supply disruption, summer normalization

## Model Training And Backtest

Training/promotion command:

```powershell
python scripts\run_daily_model_promotion.py --date 2026-07-06 --baseline-prefix price_horizon_model_20260701_mixed_approved_v3 --candidate-prefix price_horizon_model_20260706_all_items_candidate --approved-prefix price_horizon_model_20260706_all_items_checked_no365 --horizons 1,14,30,90,180 --skip-train --backtest-window-count 40 --backtest-min-train-rows 120 --robustness-samples-per-era 5 --output data\model\daily_model_promotion_20260706_all_items_checked_no365.json
```

The first full run with `365` days was rejected because there were zero valid 365-day target rows. The clean checked run excludes `365`.

Checked horizon metrics:

| Horizon | Test Direction | Backtest Direction | Test MAE | Backtest MAE |
| ---: | ---: | ---: | ---: | ---: |
| 1d | 0.8103 | 0.7900 | 0.022823 | 0.026196 |
| 14d | 0.6629 | 0.8750 | 0.092674 | 0.085158 |
| 30d | 0.6846 | 0.8250 | 0.123283 | 0.113169 |
| 90d | 0.7609 | 0.8100 | 0.117757 | 0.097798 |
| 180d | 0.8389 | 0.8650 | 0.128676 | 0.096455 |

Promotion result:

- The new candidate model was trained and backtested.
- It was not promoted because it did not beat the existing champion model consistently across test/backtest direction and MAE checks.
- The checked artifact `price_horizon_model_20260706_all_items_checked_no365` therefore uses the safe baseline champion per horizon.

This is intentional. It means the pipeline protected production from a worse model rather than blindly replacing the champion.

## Public Applicability

Strict prediction artifacts:

- `data/model/latest_price_horizon_predictions_20260706_daily_strict_candidates.json`
- `data/model/latest_price_horizon_explanations_20260706_daily_strict_candidates.json`

Predictions contain all 5 mapped crops and horizons:

- `1`
- `14`
- `30`
- `90`
- `180`

The public backend currently exposes only horizons up to 90 days. The 180-day horizon is returned under `hidden_horizons` and should stay hidden until the project has stronger long-horizon public validation.

Local API applicability check:

- Forecast endpoint returned 200 for all 5 mapped crops.
- Active public horizons: `1`, `14`, `30`, `90`
- Hidden horizon: `180`
- Model prefix returned by API: `price_horizon_model_20260706_all_items_checked_no365`

Required runtime variables for using the local artifacts:

```env
ACTIVE_PRICE_MODEL_PREFIX=price_horizon_model_20260706_all_items_checked_no365
ACTIVE_PRICE_PREDICTIONS_PATH=data/model/latest_price_horizon_predictions_20260706_daily_strict_candidates.json
ACTIVE_PRICE_EXPLANATIONS_PATH=data/model/latest_price_horizon_explanations_20260706_daily_strict_candidates.json
```

Important storage note:

- `data/model`, `data/raw`, `data/features`, `data/diagnostics`, and `data/signals` are ignored by Git.
- A code push alone will not upload these local model artifacts.
- To apply this exact result on Railway/production, either rerun the same pipeline on the server with the same env vars or upload/sync the generated artifacts through the chosen production storage path.

## Code Change In This Session

Updated `backend/app/services/horizon_forecasts.py` public helper outputs so horizon forecast explanation text is normal Korean instead of mojibake/encoding-corrupted Korean.

This improves:

- public horizon policy reason text
- direction labels
- forecast summary text
- reason group labels
- pressure-summary judgment copy

Verification:

```powershell
python -m py_compile backend\app\services\horizon_forecasts.py
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q
python scripts\run_smoke_suite.py --timeout-seconds 300
```

Result:

- 38 tests passed
- Smoke suite passed
- Local FastAPI check on `127.0.0.1:8025` returned 200 for cabbage/radish/onion/green_onion/garlic with active horizons `1,14,30,90`, hidden horizon `180`, and model version `price_horizon_model_20260706_all_items_checked_no365`.

## Immediate Next Work

1. Add metadata and API mappings for more crops.
   - Create `metadata/items/<item>.json`.
   - Add KAMIS/Agromarket/KOSIS/FarmMap code mappings.
   - Record varieties separately where the same crop has meaningful subtypes.

2. Re-run collection for newly mapped crops.
   - KAMIS and Agromarket first.
   - Settlement API should be retried with smaller batches and longer timeout because the all-item call timed out.

3. Build crop-specific feature profiles.
   - Reuse common market/weather/FarmMap features.
   - Add crop-specific physiology, storage, harvest, and import/export factors only when a source or domain rule is recorded.

4. Train and backtest again.
   - Keep 1/14/30/90 public candidate checks.
   - Keep 180 hidden.
   - Keep 365 disabled until at least 365-day target rows exist.

5. Promote only if the candidate beats the existing champion.
   - Do not replace production models merely because a new run completed.
   - Use direction accuracy, backtest direction, MAE, and temporal robustness together.

6. Fix the KAMIS mapping text encoding if the CSV is confirmed to be corrupted in the file, not only in the Windows terminal display.

## Current Readiness Judgment

For the 5 mapped crops, the pipeline is technically runnable and locally API-compatible. It is not a model upgrade because the candidate did not outperform the champion. The correct production posture is:

- safe to expose 1/14/30/90 horizons with the checked champion artifact,
- keep 180 hidden,
- do not expose 365,
- expand item coverage only after metadata and external mappings are created.
