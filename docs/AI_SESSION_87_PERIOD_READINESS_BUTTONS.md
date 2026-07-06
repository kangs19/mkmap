# AI Session 87 - Period Readiness Buttons

Date: 2026-07-06 KST

## Goal

Make the public forecast UI stop behaving as if every period is equally trusted. When the model readiness gate marks a horizon as held out, the user should see that immediately in the period controls and in the right-side forecast table.

This addresses the user concern that 1 day, 30 day, and 90 day forecasts may pass while 14 day or other periods may not. The UI now reflects that per item and per period instead of silently generating a number.

## Changed Files

- `index.html`

## Frontend Behavior

- Period buttons now have explicit `data-period` values.
- The frontend checks `LIVE_HORIZONS` and `LIVE_HORIZON_READINESS` before allowing a period to become active.
- UI periods are mapped onto the nearest public model-readiness horizons:
  - 1 week and 2 weeks use the 14 day readiness result
  - 3 weeks and 4 weeks use the 30 day readiness result
  - 2 months and 3 months use the 90 day readiness result
- If a period is held out, unavailable, or marked `insufficient_data`, the button becomes visually blocked:
  - dashed border
  - warmer warning color
  - `aria-disabled="true"`
  - title text with the public readiness reason
- If the currently selected period becomes blocked after fresh forecast data loads, the UI automatically moves to the first available period for the selected item.
- Clicking a blocked period no longer changes the map/detail forecast. Instead, the right-side policy notice shows the same public judgment message used by the forecast readiness API.

## Right Panel Forecast Cells

The compact period forecast row in the price tab now respects readiness:

- blocked horizons show `검증 대기`
- the change line shows `공개 제외`
- no synthetic price is calculated for the blocked horizon
- the cell has a title explaining why the period is not public yet

This keeps unverified horizons from looking like actual model output.

## Validation

Commands run locally:

```powershell
python scripts\run_smoke_suite.py --timeout-seconds 300
```

Result: passed.

```powershell
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q
```

Result: 38 passed, 1 warning.

Browser sanity check:

- Local static server on port 8765 loaded the dashboard successfully.
- The period buttons rendered with the new `data-period` attributes.
- The local test server was stopped after verification.

## Notes For Next Agent

- Do not expose held-out periods as forecast numbers in any new UI surface.
- Keep the readiness contract consistent:
  - `held_out: true`
  - `available: false`
  - `data_status: insufficient_data`
  - public message from `horizonBlockedMessage(...)`
- The next useful step is a focused UI pass over forecast availability wording in the map hover card and region detail header, so every surface says the same thing when a horizon is not public.
- Generated artifacts under `data/` are diagnostics and should not be committed unless the user explicitly asks.
