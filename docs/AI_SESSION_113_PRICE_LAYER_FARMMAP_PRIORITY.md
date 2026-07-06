# AI Session 113 - Price Layer FarmMap Priority

Date: 2026-07-06

## User Issue

When selecting `가격 예측` in the left map filters, crop regions did not appear clearly on the map.

## Cause

The FarmMap land-use layer had higher style priority than the crop price/production layers.

When `팜맵 농지분류` was enabled, the province/city style code returned FarmMap colors before applying crop-region price colors. This could make it look like the `가격 예측` layer was selected but crop areas were not shown.

## Changes

- Removed FarmMap color override from `modeColor()` and `modeCityColor()`.
- Province map styling now prioritizes active crop price/production colors.
- City map styling now prioritizes active crop price/production colors.
- FarmMap remains visible only as a secondary overlay:
  - Non-crop areas can still use FarmMap land-use color.
  - Crop areas keep price/production fill and use stronger green border/dash to show FarmMap overlap.
- Hover behavior now keeps crop price/cultivation cards for active crop areas, even when FarmMap is enabled.

## QA

- Browser QA on local app:
  - Enabled `팜맵 농지분류` while `가격 예측` was active.
  - Crop pins remained visible.
  - Active crop areas kept price forecast fill colors.
  - FarmMap overlap showed as green border/dash instead of replacing the price layer.
  - No visible page error was detected.
- `python scripts\audit_frontend_launch_ui.py` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.

## Remaining Notes

- Local DB did not contain operating regional market prices, so the browser QA used static crop-region map data for visual layer priority.
- Production regional price API is separately covered by the Session 112 `regional_prices` launch-readiness check.

