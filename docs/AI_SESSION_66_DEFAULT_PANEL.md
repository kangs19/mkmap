# Session 66 - Default Right Panel Market Check (2026-07-05)

## Why

When no map region is selected, the right panel previously showed `오늘의 AI 브리핑`.
The content felt generic and did not help users decide what to inspect next.

The default panel should behave like a market command board:

- show what data is actually available now.
- avoid invented AI conclusions when verified forecast/price rows are missing.
- guide users toward useful next clicks on the map.

## What Changed

Updated `index.html`.

- Renamed the default right panel to `오늘의 시장 체크`.
- Replaced generic AI wording with market/status wording.
- Added `오늘 볼 체크포인트`.
- Kept live risk ranking as the first priority when forecast signals exist.
- Added fallback cards when forecast signals are not ready:
  - verified price cards if national prices exist.
  - representative crop-production province cards if prices are also missing.
- Added `데이터 상태` rows:
  - prediction signal status.
  - baseline price status.
  - map production coverage status.
  - regional market price status.
- Made representative province fallback cards clickable through `zoomProvinceByCode(...)`.
- Reworded market-price status to say: measured wholesale-market average first, representative market basis when regional measured data is unavailable.

## Product Rule

Do not show a confident AI conclusion unless the API/model supplied a verified value.

If live forecast data is missing, the UI should clearly show:

- representative production regions.
- available price API state.
- whether map regions are verified representative areas, not the only producing areas.
- what the user can click next.

## Verification

- `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Local browser check at `http://127.0.0.1:8017/` showed:
  - `오늘의 시장 체크`.
  - representative crop province cards.
  - data-status rows.
  - no captured runtime errors.
- Clicking a default checkpoint card produced no app runtime errors.

## Next UX Work

- Replace the emoji-based header icon with an icon component if the frontend moves to a component framework.
- Add a small timestamp/source label beside each price card once the live regional price API is reliably populated.
- Consider adding a "latest collection status" row from backend health/admin diagnostics so users can tell whether APIs are fresh today.
