# AI Session 70 - Cultivation And Market Tab

Date: `2026-07-05`

## User Feedback

The `재배·시장` tab was not useful enough. It mainly showed cautionary explanatory text such as "not all uncolored regions mean no shipment" and "data validation basis". The user wants the tab to behave like an analytical market panel, not a disclaimer panel.

## Change Made

- Replaced the visible explanation-first content in the selected region detail panel with compact analytical indicators:
  - national shipment rank,
  - in-province shipment share,
  - price influence label,
  - shipment stability score,
  - in-province shipment ranking table,
  - monthly shipment concentration bars,
  - annual shipment volume,
  - reference wholesale market.
- Hid the generic `데이터 검증 기준` note in this tab because it repeated low-value caveats.
- Added reusable UI helpers in `index.html`:
  - `fmtTon`
  - `cropRegionRows`
  - `rankBy`
  - `seasonProfileMonths`
  - `miniMonthBars`
  - `marketPowerLabel`

## Data Semantics

The new panel uses currently available region/item metadata and live price context where present:

- `shipment_ton` or `production_ton` is used as the local supply-volume proxy.
- National and provincial ranks are computed from active crop city rows only.
- Monthly bars currently use `main_season` as a metadata-based seasonal profile. They are not yet measured monthly shipment rows.
- Price influence is a heuristic from supply share, price gap, and YoY movement.
- Shipment stability is a heuristic from YoY movement, risk score, and harvest rate.

Do not present these derived labels as official quality grades. They are decision-support signals until official monthly shipment and quality datasets are attached.

## Still Needed

1. Connect real monthly shipment/auction history from the agromarket APIs.
2. Replace seasonal-profile bars with measured monthly shipment bars once history is normalized.
3. Add official wholesale-market attribution per selected region and item, not only fallback reference market.
4. Add crop-specific quality proxies only when backed by data, for example:
   - grade/class counts from auction rows,
   - high-grade share,
   - average unit price premium versus same item national average,
   - rejected/missing-grade ratio if provider exposes it.
5. Add API/source badges for each metric so the user can tell official, live, model, and metadata values apart without reading a paragraph.

## Verification

- `python -m pytest tests\test_api.py -q`: passed, `33 passed`.
- `python scripts\run_smoke_suite.py --timeout-seconds 300`: passed.
- Browser smoke on `http://127.0.0.1:8022/index.html`: page loaded and base interactions remained functional.
- Local `node.exe` syntax command could not run because Windows returned `Access is denied`; browser load was used instead for frontend runtime validation.

