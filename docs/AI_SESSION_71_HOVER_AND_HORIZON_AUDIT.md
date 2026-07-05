# AI Session 71 - Hover And Horizon Audit

Date: `2026-07-05`

## User Questions

- Map hover popups still did not appear reliably.
- Forecast cards looked monotonic: crops that rise keep rising and crops that fall keep falling.
- 180-day and 365-day forecasts seemed trained earlier but were not visible in the UI.

## Findings

- Province-level SVG paths did not receive the custom fallback hover binding. City-level paths had a binding attempt, but SVG path custom properties were not reliable in the browser environment.
- The UI previously derived period forecasts mostly from one probability/region-price signal and scaled it by period. That can make each crop look one-directional across all periods.
- Local model artifacts include horizon outputs for `1, 30, 90, 180, 365` days in `data/model/latest_price_horizon_predictions_20260701_mixed_approved_v3_temporal_strict_candidates.json`.
- Production `https://mk-map.com/api/v1/items/cabbage/forecast` currently returns DB-backed 14-day forecast only, not the local horizon artifact.
- Production `https://mk-map.com/api/v1/items/cabbage/forecasts` currently exposes `7, 14, 21, 28, 60, 90`; `60` and `90` can be marked `insufficient_data`, and `180/365` are not in the production DB response yet.

## Changes Made

- Added fallback hover binding for province-level map paths as well as city paths.
- Replaced fragile SVG custom-property lookup with a `WeakMap` for tooltip handlers.
- Added frontend support for active horizon payloads:
  - first tries `/api/v1/items/{item_code}/forecast`,
  - falls back to `/api/v1/items/{item_code}/forecasts` if the first response has no `forecast.horizons`.
- Forecast period changes now prefer horizon-specific model values when available.
- If a horizon row only has probability, the UI derives change direction from `up_probability` instead of blindly trusting a direction label.
- Added UI slots for `6M` and `1Y`. These are ready for 180/365 horizon artifacts, but production still needs those horizons deployed or imported.

## Remaining Work

1. Deploy or import approved 180/365 horizon artifacts to production.
2. Fix production model rows where `direction` and `up_probability` disagree, for example `direction=up` with `up_probability=0.2`.
3. Add a visible data-status badge per horizon:
   - `model`,
   - `interpolated`,
   - `insufficient`,
   - `not deployed`.
4. Replace probability-to-price-change heuristic for DB-only horizon rows with real predicted change columns.

## Verification

- `python -m pytest tests\test_api.py -q`: passed, `33 passed`.
- `python scripts\run_smoke_suite.py --timeout-seconds 300`: passed.
- Browser check:
  - map path count: `17`,
  - fallback-bound path count: `17`,
  - period buttons include `6M` and `1Y`,
  - forecast cells `rp-p180` and `rp-p365` exist.

