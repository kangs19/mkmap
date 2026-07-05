# Session 67 - Risk Score Contract And UI Consistency (2026-07-05)

## User Problem

The hover popup `주요 리스크` and the right-panel `가격 변동 리스크` looked different.
The UI also did not explain what a high or low risk score meant, or whether the numbers were learned/model-based, derived, or arbitrary.

## Decision

Risk display must follow one contract:

- A score is 0-100.
- Higher means greater price-volatility or supply-stress risk for the selected crop/region/period.
- The same region should not show different component scores in the hover popup and the right detail panel.
- Every component should show whether it is live data or a derived/model value.
- The UI should avoid pretending a missing live signal is observed data.

## Implementation

Updated `index.html`.

- Added shared helpers:
  - `riskLevelInfo(score)`
  - `riskSourceTag(source)`
  - `buildRiskBreakdown(d, priceCtx, chgPct)`
  - `riskBarsHtml(rows, options)`
- The right-panel forecast risk section now re-renders from `buildRiskBreakdown(...)`.
- The hover popup `주요 리스크` now also uses `buildRiskBreakdown(...)`.
- Added a right-panel explanation block:
  - explains 0-100 meaning.
  - explains backend signal formula when live region risk exists.
  - explains fallback map score basis when backend region risk does not exist.
  - explicitly says missing live data is not displayed as measured data.

## Current Risk Basis

Backend `RegionSignal` formula:

- price signal: 50%
- weather signal: 35%
- production/KOSIS supply signal: 15%

When no backend region signal is available on the static map, the visible score is a derived map score based mainly on price index and shipment year-over-year movement.

The component bars are explanatory decomposition, not independent official API fields:

- `기상·재해`: live region signal when available, otherwise derived from the overall score.
- `출하·생육`: shipment YoY, harvest progress, and production-region pressure.
- `시장·가격`: regional market price when available, otherwise forecast change and price-index pressure.

## Verification

- `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Local browser load at `http://127.0.0.1:8018/` had no captured runtime errors.

## Remaining UX Follow-up

The older inline risk-decomposition code still exists before the new unified render override in `showRegionDetail(...)`.
It is visually overridden now, but a later cleanup should remove the dead branch once the map UI is moved into smaller components.
