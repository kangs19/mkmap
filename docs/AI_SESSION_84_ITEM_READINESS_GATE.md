# Session 84 - Item-Level Forecast Readiness Gate (2026-07-06)

## Purpose

The 20-crop candidate model proved that many crops can be trained, but it also showed that weak or draft crops can damage public model confidence if everything is judged as one group.

This session added an item-level readiness audit so each crop and horizon can be judged separately before public exposure.

## Added Script

Added `scripts/audit_item_forecast_readiness.py`.

It combines:

- Metadata source flags from `metadata/items/*.json`.
- Local feature cache coverage from `data/features`.
- Target row counts from the training table.
- Per-item horizon backtest metrics from model backtest JSON files.

Default output:

```powershell
data/diagnostics/item_forecast_readiness_<YYYYMMDD>.json
```

## Scoring Logic

The readiness score is intentionally conservative.

Signals used:

- Price target history.
- Regional market price context.
- KOSIS or production-region mapping.
- KMA/RDA agricultural weather mapping and cache coverage.
- Disaster/event context.
- Metadata manual review status.
- Forecast context availability.

Each horizon is also judged separately using:

- Target rows for that horizon.
- Backtest direction accuracy.
- Backtest prediction count.

The script labels items as:

- `candidate`: can be considered for public prediction after human review of item-level charts.
- `watch`: keep experimental or low-confidence only.
- `hold`: do not expose as a trusted public forecast yet.

## 20-Crop Agromarket Candidate Audit

Command:

```powershell
python scripts\audit_item_forecast_readiness.py --date 2026-07-06 --start 2025-07-06 --model-prefix price_horizon_model_20260706_20items_at_candidate --output data\diagnostics\item_forecast_readiness_20260706_20items_at_candidate.json
```

Result:

| Status | Count |
| --- | ---: |
| candidate | 5 |
| hold | 15 |

Candidate items:

- `cabbage`
- `garlic`
- `green_onion`
- `onion`
- `radish`

Hold items:

- `apple`
- `carrot`
- `chamoe`
- `cucumber`
- `fresh_pepper`
- `lettuce`
- `pear`
- `pepper`
- `perilla`
- `potato`
- `sesame`
- `spinach`
- `sweet_potato`
- `tomato`
- `watermelon`

Interpretation:

- The readiness gate correctly keeps the original 5 better-mapped crops as candidates.
- The 15 newly added crops stay on hold because most are still missing verified KOSIS production mapping, KMA crop-weather mapping, regional/event context depth, and metadata review.
- This supports the current production policy: do not publish the 15 added crops as trusted forecasts yet.

## Horizon-Level Findings

Even candidate crops are not uniformly ready for every forecast horizon.

Examples from the 20-crop Agromarket candidate audit:

| Item | Candidate horizons | Hold horizons |
| --- | --- | --- |
| cabbage | 1d, 30d, 180d | 14d, 90d |
| garlic | 1d, 14d, 30d, 90d | 180d |
| green_onion | 14d, 30d, 90d, 180d | 1d |
| onion | 1d, 14d, 30d, 90d, 180d | none |
| radish | 1d, 14d, 90d, 180d | 30d |

This means the public API/UI should eventually expose forecast confidence by item and horizon, not only by item.

## Why This Matters

Before this gate, a 20-crop model could produce predictions for all crops, but users could not tell which crops were backed by verified data and which were only draft experiments.

Now the project can answer:

- Which crops are safe candidates?
- Which horizons are weak for a crop?
- Which missing data source is blocking a crop?
- Which crops should be prioritized for KOSIS/KMA/FarmMap mapping next?

## Next Work

1. Add this readiness report to the daily model promotion pipeline.
   - It should run after candidate model training and before public artifact promotion.

2. Add public artifact filtering by item and horizon.
   - A crop can be visible for one horizon and hidden for another.
   - Low-confidence or held horizons should not look like normal predictions.

3. Add backend/UI support for readiness labels.
   - Show only useful user-facing judgment, not technical labels.
   - Example: "이 기간 예측은 아직 공개 판단에 쓰기 어렵습니다."

4. Improve the 15 held crops.
   - Verify KOSIS production/area mappings.
   - Verify KMA crop-weather PA_CROP_SPE_ID and AREA_ID mappings.
   - Build FarmMap crop-region summaries.
   - Re-run this readiness audit after each source is added.

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
