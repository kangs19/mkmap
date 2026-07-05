# AI Session 72 - Top Navigation Panels

Date: `2026-07-05`

## User Feedback

The top navigation buttons `가격 예측 설명` and `대시보드` used a good right-panel style, but the content was too thin to be useful.

## Change Made

- Rebuilt the forecast explanation panel as a compact model-inspection panel:
  - current item forecast engine summary,
  - price/region/risk/horizon data status,
  - horizon-by-horizon availability table,
  - calculation flow for base price, horizon direction, and shared map/popup/detail basis.
- Rebuilt the dashboard panel as a compact work queue:
  - forecast item count,
  - price-feed count,
  - horizon-model count,
  - watch-item count,
  - priority item cards,
  - today action list,
  - top-risk summary.
- Promoted the priority item list from a local `TOP5` variable inside `window.onload` to global `PRIORITY_ITEMS`, so dashboard rendering can use the same list safely.

## Implementation Note

For stability, these two new panels currently use mostly ASCII/English labels. The existing `index.html` has a history of mojibake-sensitive string edits, so future Korean copy should be moved into a small UTF-8-safe dictionary or JSON block rather than repeatedly editing mixed inline template strings.

## Verification

- `python -m pytest tests\test_api.py -q`: passed, `33 passed`.
- `python scripts\run_smoke_suite.py --timeout-seconds 300`: passed.
- Browser check:
  - `가격 예측 설명` renders the forecast engine panel.
  - `대시보드` renders the dashboard panel.

