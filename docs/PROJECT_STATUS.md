# MK Map Project Status

Last updated: 2026-06-30

## Current State

The project now has a metadata-driven agriculture risk and price forecast pipeline for the first five tracked items:

- cabbage
- radish
- onion
- green_onion
- garlic

The end-to-end flow can collect or reuse cached external data, build regional risk signals, train a price model, create risk-adjusted price predictions, import outputs into the FastAPI backend, and expose the results through public and admin API endpoints.

## Completed

### Repository And Deployment Wiring

- GitHub repository is active at `https://github.com/kangs19/mkmap`.
- Backend is designed to run behind `https://mk-map.com`.
- Railway deployment config exists in `railway.toml` and uses the root `Dockerfile`.
- Railway start command is `/app/start.sh`, which runs `uvicorn app.main:app` on `${PORT:-8100}`.
- Deployment runbook exists at `docs/DEPLOYMENT_RUNBOOK.md`.
- FastAPI backend exposes user-facing forecast, signal, map, and admin endpoints.
- Admin routes are available under `/api/v1/admin/...`.
- Daily scheduler runs the metadata pipeline at `06:00` KST.
- Admin UI can run the metadata pipeline manually and poll status.

### Metadata And Engine Structure

- Item metadata exists for the initial five crops.
- Metadata validation is automated with `scripts/validate_metadata.py`.
- External mapping validation is automated with `scripts/validate_external_mappings.py`.
- Item metadata supports extensible feature-engine profiles, weather risk windows, price mappings, production mappings, and event mappings.

### External Data Pipelines

- KAMIS price feature collection is wired.
- KOSIS production feature collection is wired.
- KMA/data.go.kr event feature collection is wired.
- KMA crop-weather collection is wired with mapping validation.
- Cached connectors allow downstream model work even when live collection is skipped.

### Risk Signal Pipeline

- Region-level risk signals are generated from feature bundles.
- Signals are exported to `data/signals/{YYYYMMDD}/region_risk_signals.json`.
- Backend import writes region signals into `region_signals`.
- User-facing routes read imported signals:
  - `GET /api/v1/signals/today`
  - `GET /api/v1/items/{item_code}/signals`
  - `GET /api/v1/map/signals`
  - `GET /api/v1/dashboard/cards`
  - `GET /api/v1/alerts/high-risk`

### Price Forecast Pipeline

- Price training tables include lag, momentum, moving-average gap, volatility, and calendar features.
- The model trains a global standardized linear baseline.
- Item-specific models are trained only when they beat the global fallback on holdout rows.
- Item-specific model acceptance now records a gate summary and rejects short-history models that do not clearly improve on the global fallback.
- Direction thresholds are tuned on holdout data.
- Forecast probability calibration is derived from rolling backtest MAE and direction accuracy instead of only raw predicted price change.
- Risk overlays are applied after pure price-history prediction.
- Forecast imports write five daily forecasts into the backend.
- Forecast API exposes:
  - `model_version`
  - `model_scope`
  - forecast probabilities
  - confidence reason and confidence factors
  - top factors
- Public forecast explanation API exposes headline, model scope, reasons, top risk regions, and data freshness in a frontend-friendly Korean payload.

### Admin And Evaluation

- Admin UI includes:
  - status dashboard
  - data freshness status for prices, weather, region signals, and forecasts
  - forecast status
  - manual metadata pipeline run
  - model evaluation tab
  - API key management
  - usage logs
- Model evaluation report is generated at `data/model/price_baseline_model_{YYYYMMDD}_evaluation.json`.
- Rolling backtest report is generated at `data/model/price_baseline_model_{YYYYMMDD}_backtest.json`.
- Admin API exposes `GET /api/v1/admin/model-evaluation`.
- Forecast scope contract smoke test verifies item/global scope traceability.
- API service catalog Korean display names are normalized for admin/debug output.
- API service catalog reports readiness and next setup action per external service.
- API service catalog now has confirmed endpoint defaults for AT regional price and KMA heat-wave impact forecast.
- Text encoding health check guards metadata, connector, script, and docs files against mojibake regressions.
- Admin status API returns `data_freshness` with latest date, lag days, and freshness status per core dataset.
- Admin weather freshness distinguishes KMA crop-weather provider delay, fallback dates, and true missing data.

## Latest Verified Run

Date: `2026-06-30`

- `region_signals`: 85 imported rows
- `forecasts`: 5 imported rows
- price model train rows: 120
- price model test rows: 30
- feature count: 20
- tuned direction threshold: `0.025`
- MAE: `0.017679`
- RMSE: `0.021859`
- sign accuracy: `0.5333`
- 3-class direction accuracy: `0.8333`
- accepted item models: 1
- accepted item model: garlic
- global fallback used for: cabbage, radish, onion, green_onion
- Price model training now writes a rolling backtest summary into the evaluation report and a detailed backtest JSON next to the model.

## Latest Live API Diagnostic

Date: `2026-06-30`

- KAMIS price: live OK for cabbage, 28 recent price features.
- KOSIS production: live OK for cabbage, 17 region production features using 2025 data.
- KMA crop main-area weather: live OK with date fallback, 12 sampled weather features.
- KMA weather alert: provider still returned `DB_ERROR` across 12 combinations when rechecked on 2026-06-30.
- KMA typhoon: provider responded with `NO_DATA` for the requested date; diagnostics classify this separately from provider errors.
- KMA impact forecast: live OK, 10 normalized impact forecast rows with region code, level, and severity score.
- KMA midterm forecast: live OK, 1 normalized forecast event row.
- Service catalog: live diagnostics now attach service code, provider, display name, configured/missing env, operation, metrics, and next action.
- Untested approved services are listed separately as `not_tested`, including AT settlement/regional price, RDA agri weather, satellite, and weather chart.
- Service readiness summary now has 2 endpoint-required services, 1 missing-env endpoint-verified service, 6 configured services, 1 configured mapping-required service, and 2 optional services.
- Admin status UI now shows the latest live API diagnostic summary and per-service next actions.
- Live diagnostic summary: 8 checks, 6 OK, 1 provider API error, 1 no-data response, 0 timeout, 0 failed.

## Main Commands

Run the full daily pipeline:

```powershell
python scripts\run_meta_pipeline.py --date 2026-06-30
```

Reuse cached feature data:

```powershell
python scripts\run_meta_pipeline.py --date 2026-06-30 --skip-collect
```

Run the local fast smoke suite:

```powershell
python scripts\run_smoke_suite.py
```

Check text encoding health only:

```powershell
python scripts\check_text_encoding_health.py
```

Run live API diagnostics:

```powershell
python scripts\run_live_api_diagnostics.py --date 2026-06-30 --item cabbage
```

Include slower API contract and risk signal checks:

```powershell
python scripts\run_smoke_suite.py --include-slow --timeout-seconds 120
```

## Current Guardrails

- Real API keys are not committed.
- Generated files under `data/` are ignored by Git.
- Backend imports are idempotent per `item_code + date`.
- Forecast model scope is visible via API.
- Top factors remain price/risk factors and are not polluted by trace metadata.
- Item models are accepted only when they pass the quality gate against global fallback.
- Public forecast explanations are available through `/forecast-explanation`.
- Public dashboard cards are available through `/api/v1/dashboard/cards`.
- High-risk alert candidates are available through `/api/v1/alerts/high-risk`.

## Next Work

### High Priority

- Monitor KMA weather alert until provider-side `DB_ERROR` clears.
- Confirm AT regional price runtime env and add its live diagnostic.

### Model Improvement

- Keep accumulating daily price history.

