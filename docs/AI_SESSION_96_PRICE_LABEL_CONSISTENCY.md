# Session 96 - Price Label Consistency

Date: 2026-07-06

## Goal

Continue map/detail QA by reducing confusion between current prices and forecast prices.

## Finding

Map pins can display forecast-adjusted prices, while SVG path titles and the right detail panel can display current/base prices.

The numbers can legitimately differ, but the UI text needed to say which number is current and which number is forecast.

## Changes

- `index.html`
  - Province path title now says `현재 평균`.
  - City path title now says `현재`.
  - Region pin title/data-tooltip now says `예측 도매가` or `예측 소매가` where the value is forecast-adjusted.
  - Blocked horizon pin title now says `현재 ... · 검증 대기`.
  - Right detail panel current-price line now labels the current basis as `현재 도매가` or `현재 소매가`.

## Validation

- `python scripts/run_smoke_suite.py --timeout-seconds 300`
  - Passed

## Next QA Slice

1. Verify production pin/detail labels after deploy.
2. Continue right-panel tab density and usefulness QA.
3. Check mobile detail panel after selecting a city.
