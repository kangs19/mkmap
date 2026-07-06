# AI Session 89 - Readiness Count Consistency

Date: 2026-07-06 KST

## Goal

Continue autonomous cleanup after map readiness gating. The next issue was consistency: the top explanation/statistics panels counted horizons as available when `available !== false` and `data_status !== insufficient_data`, but that missed `held_out: true`.

That could make a horizon excluded by backtest stability appear as usable in top-level statistics.

## Changed Files

- `index.html`

## Changes

- Added `isPublicForecastHorizon(row)` as the shared frontend readiness predicate.
- The predicate requires:
  - a row exists
  - `held_out !== true`
  - `available !== false`
  - `data_status !== "insufficient_data"`
- `renderExplanationPanel()` now uses the shared predicate for available/blocked horizon counts.
- `renderDashboardPanel()` now uses the shared predicate for each crop's available forecast-period count.
- `hiddenHorizonDays()` now treats any non-public row as hidden, including `held_out` and insufficient data.
- `isHorizonBlocked()` and `horizonRowChangePct()` now use the same predicate, reducing drift between UI surfaces.

## Validation

Commands run locally:

```powershell
git diff --check
python scripts\run_smoke_suite.py --timeout-seconds 300
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q
```

Result:

- whitespace check passed
- smoke suite passed
- backend forecast/API tests passed: 38 passed, 1 warning

## Next Useful Step

The next autonomous UI task should be a browser-level check of blocked periods across:

- period buttons
- map pins
- hover cards
- right forecast row
- top explanation panel
- statistics panel

If browser automation is unavailable, continue static cleanup by replacing duplicated readiness wording with one shared message builder.
