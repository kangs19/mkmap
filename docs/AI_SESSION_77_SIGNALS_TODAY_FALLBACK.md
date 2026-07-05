# AI Session 77 - Signals Today Latest Forecast Fallback

Date: 2026-07-06 KST

## Problem

After the UI trust/statistics deployment, the production page loaded correctly but the left `전국 위험 현황` list still showed `—` for every item and displayed `AI 예측 데이터가 아직 없습니다`.

Live checks showed:

- `/api/v1/signals/today` returned `items: []` with `base_date: 2026-07-06`.
- `/api/v1/items/cabbage/forecast` returned a valid forecast with `base_date: 2026-07-05`.

The forecast endpoint already falls back to the latest forecast when today has no exact row. The `signals/today` endpoint did not.

## Fix

Updated `backend/app/routers/signals.py`:

- Look up the latest available `Forecast.base_date <= today`.
- Look up the latest available `RegionSignal.date <= today`.
- Use the newest available data date as `base_date`.
- Use today only when neither forecasts nor region signals exist.

This allows the public dashboard/sidebar to show yesterday's latest forecast until the daily retrain produces today's rows.

## Regression Test

Added `test_signals_today_uses_latest_forecast_when_today_is_empty` in `backend/tests/test_api.py`.

The test clears today rows, inserts a forecast for yesterday, calls `/api/v1/signals/today`, and verifies:

- response `base_date` is the latest available forecast date,
- the inserted item appears,
- direction/probability/risk level are derived correctly.

## Verification

- `python -m pytest tests/test_api.py -q`: 35 passed.
- `python scripts/run_smoke_suite.py --timeout-seconds 300`: passed.

## Next Check After Deploy

After deployment, verify:

- `/api/v1/signals/today` returns non-empty `items`.
- `https://mk-map.com` no longer shows `AI 예측 데이터가 아직 없습니다` when latest forecast rows exist.
- `통계` panel rankings use live forecast values instead of all-zero placeholders.
