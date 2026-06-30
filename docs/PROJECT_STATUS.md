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

### Price Forecast Pipeline

- Price training tables include lag, momentum, moving-average gap, volatility, and calendar features.
- The model trains a global standardized linear baseline.
- Item-specific models are trained only when they beat the global fallback on holdout rows.
- Direction thresholds are tuned on holdout data.
- Risk overlays are applied after pure price-history prediction.
- Forecast imports write five daily forecasts into the backend.
- Forecast API exposes:
  - `model_version`
  - `model_scope`
  - forecast probabilities
  - top factors

### Admin And Evaluation

- Admin UI includes:
  - status dashboard
  - forecast status
  - manual metadata pipeline run
  - model evaluation tab
  - API key management
  - usage logs
- Model evaluation report is generated at `data/model/price_baseline_model_{YYYYMMDD}_evaluation.json`.
- Admin API exposes `GET /api/v1/admin/model-evaluation`.
- Forecast scope contract smoke test verifies item/global scope traceability.

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

## Latest Live API Diagnostic

Date: `2026-06-30`

- KAMIS price: live OK for cabbage, 14 recent price features.
- KOSIS production: live OK for cabbage, 17 region production features using 2025 data.
- KMA typhoon: live OK, 2 normalized event rows.
- KMA midterm forecast: live OK, 1 normalized forecast event row.
- KMA crop main-area weather: unstable; latest diagnostic hit the 45 second timeout.
- KMA weather alert: provider returned `DB_ERROR`.
- Service catalog: 12 cataloged services, 4 currently configured by environment.

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

## Next Work

### High Priority

- Add stronger live collection diagnostics for each external API service.
- Fix mojibake in `config/api_services.json` Korean display names.
- Expand KMA crop-weather mapping from candidate regions to confirmed official codes.
- Add API/data freshness status to the admin dashboard.
- Add a public-facing forecast explanation view that shows model scope, risk factors, and data freshness in Korean.

### Model Improvement

- Keep accumulating daily price history.
- Add a rolling backtest report across multiple dates.
- Add item-specific feature gates so unstable item models need more history before acceptance.
- Calibrate forecast probability from historical error instead of only predicted price change.

### Product/API

- Add a compact public endpoint for dashboard cards.
- Add forecast confidence reasons, not only `low/medium/high`.
- Add alert thresholds for high-risk region/item combinations.
- Add deployment notes for syncing `.env` and scheduler behavior on the production server.
