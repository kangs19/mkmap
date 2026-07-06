# Session 85 - Readiness-Based Prediction Filtering (2026-07-06)

## Purpose

Session 84 created an item-level readiness report. This session connected that report to prediction artifacts so public API/UI output can be filtered by item and horizon.

The goal is:

- Keep experimental predictions available for diagnostics.
- Mark weak item/horizon forecasts as `held_out`.
- Let the backend hide held horizons from normal public responses.
- Prevent draft crops from looking like trusted forecasts just because the model can output a number.

## Code Changes

Updated `scripts/predict_price_horizons.py`.

New arguments:

```powershell
--readiness-report <path>
--only-readiness-candidates
```

When a readiness report is supplied:

- Each item receives `readiness_status`, `readiness_score`, and `readiness_reasons`.
- Each horizon receives:
  - `held_out`
  - `available`
  - `readiness_status`
  - `readiness_reasons`
  - `readiness_gate`

When `--only-readiness-candidates` is used:

- Only item/horizon rows marked `candidate` by `audit_item_forecast_readiness.py` remain public-available.
- `watch` and `hold` rows are still kept in the artifact, but marked `held_out: true`.

Updated `scripts/explain_price_horizon_predictions.py`.

- Explanation rows now preserve readiness fields from the prediction artifact.
- This allows future UI/API responses to explain why a horizon was held out.

Updated `scripts/run_daily_model_promotion.py`.

- Adds an `item_readiness` step after approved model quality checks.
- Passes the readiness report into both warn and strict prediction generation.
- Uses `--only-readiness-candidates` so public artifacts can respect item/horizon readiness.
- Adds the readiness report path to the run summary artifacts.

## Local Validation Against 20-Crop Candidate

Command:

```powershell
python scripts\predict_price_horizons.py --features data\model\price_training_table_20260706.csv --models-dir data\model\horizons --model-prefix price_horizon_model_20260706_20items_at_candidate --quality-report data\model\horizons\price_horizon_model_20260706_20items_at_checked_quality_temporal_warn.json --readiness-report data\diagnostics\item_forecast_readiness_20260706_20items_at_candidate.json --only-readiness-candidates --horizons 1,14,30,90,180 --output data\model\latest_price_horizon_predictions_20260706_20items_at_readiness_test.json
```

Result:

- Prediction artifact generated successfully.
- All 20 items are still present for diagnostics.
- Public-available horizons are now filtered by readiness.

Public-available horizons at or below 90 days:

| Item | Available horizons |
| --- | --- |
| cabbage | 1d, 30d |
| garlic | 1d, 14d, 30d, 90d |
| green_onion | 14d, 30d, 90d |
| onion | 1d, 14d, 30d, 90d |
| radish | 1d, 14d, 90d |

All 15 newly added draft crops currently have no public-available horizon because their readiness status is still `hold`.

Explanation generation was also validated:

```powershell
python scripts\explain_price_horizon_predictions.py --features data\model\price_training_table_20260706.csv --models-dir data\model\horizons --model-prefix price_horizon_model_20260706_20items_at_candidate --predictions data\model\latest_price_horizon_predictions_20260706_20items_at_readiness_test.json --quality-report data\model\horizons\price_horizon_model_20260706_20items_at_checked_quality_temporal_warn.json --output data\model\latest_price_horizon_explanations_20260706_20items_at_readiness_test.json
```

Result:

- Explanation artifact generated successfully for 20 items.

## Backend Impact

The backend already hides horizon rows with `held_out`.

This change means future prediction artifacts can carry item-level and horizon-level readiness without requiring an immediate backend rewrite.

Expected public behavior:

- Held horizons are excluded from `forecast.horizons`.
- Held days appear in `hidden_horizons`.
- Explanation data can later show a user-friendly reason for why a period is unavailable.

## Product Interpretation

This is the important trust-control layer.

Without it:

- A weak new crop could display a confident-looking forecast.
- Users could confuse experimental coverage with production readiness.

With it:

- The system can train broadly but publish narrowly.
- New crops can be added safely as data improves.
- Public confidence can be controlled per crop and per forecast period.

## Next Work

1. Add user-facing Korean messages for readiness holds.
   - Do not show technical labels such as `low_backtest_direction`.
   - Translate into judgment text such as "이 기간은 과거 검증에서 방향성이 불안정해 공개 예측에서 제외했습니다."

2. Add UI treatment for held horizons.
   - Hide unavailable period chips or show them disabled with a short reason.
   - Avoid showing large forecast cards for unavailable horizons.

3. Add backend response fields for readiness summary.
   - Public API can expose a compact `readiness` object without leaking noisy diagnostics.

4. Improve the 15 held crops.
   - KOSIS mapping.
   - KMA crop-weather mapping.
   - FarmMap crop-region summaries.
   - Re-run readiness and prediction filtering after each feature-source improvement.

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
