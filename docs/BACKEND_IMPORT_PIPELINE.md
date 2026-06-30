# Backend Import Pipeline

This bridge imports generated `mkmap_meta` outputs into the existing FastAPI backend database tables.

## Inputs

- Signals: `data/signals/{YYYYMMDD}/region_risk_signals.json`
- Predictions: `data/model/latest_price_predictions_{YYYYMMDD}_risk.json`

These generated files are ignored by Git. The import script reads them and writes:

- `region_signals`
- `forecasts`

## Command

```powershell
python scripts\import_meta_outputs_to_backend.py --date 2026-06-30
```

Explicit paths can be passed when needed:

```powershell
python scripts\import_meta_outputs_to_backend.py `
  --date 2026-06-30 `
  --signals data\signals\20260630\region_risk_signals.json `
  --predictions data\model\latest_price_predictions_20260630_risk.json
```

## Transformations

- `risk_score`: converted from `0..1` to backend `0..100`.
- `risk_level`: `watch` becomes `caution`, `critical` becomes `high`.
- `price_effect`: upward/downward/stable variants become `up`, `down`, or `neutral`.
- Forecast direction: `stable` becomes backend `neutral`.
- Forecast probabilities are derived from risk-adjusted predicted price change.
- Existing rows for the same `item_code + date` are deleted before insert, so repeated imports are idempotent for the target day.

## Current Run

`2026-06-30` local import succeeded:

- `region_signals`: 85 rows
- `forecasts`: 5 rows

The existing backend routes then read these tables:

- `GET /api/v1/signals/today`
- `GET /api/v1/items/{item_code}/signals`
- `GET /api/v1/map/signals?item_code=cabbage`
- `GET /api/v1/items/{item_code}/forecast`

If the server has already cached `/api/v1/signals/today`, wait up to 5 minutes or restart the API process after import.

## End-To-End Runner

For a full daily run:

```powershell
python scripts\run_meta_pipeline.py --date 2026-06-30
```

To reuse already collected `data/features` files and only rebuild downstream outputs:

```powershell
python scripts\run_meta_pipeline.py --date 2026-06-30 --skip-collect
```

For a faster daily run when the KMA crop-weather gateway is slow, cap the number of
weather requests sampled per item:

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --weather-lookback-days 3 --weather-max-requests-per-item 16 --weather-request-timeout-seconds 8
```

`2026-07-01` local validation with cached collection outputs completed through risk
signals, model training, and risk-adjusted predictions without backend import.

## Backend Admin And Scheduler

The FastAPI backend exposes the runner through admin endpoints:

- `POST /api/v1/admin/meta-pipeline/run`
- `GET /api/v1/admin/meta-pipeline/status`

Both routes require the configured `X-Admin-Key` header.

The backend scheduler also runs the same metadata-driven pipeline every day at `06:00` KST. After a successful run it clears the cached signal/report responses and sends the daily Discord notification when a webhook is configured.
