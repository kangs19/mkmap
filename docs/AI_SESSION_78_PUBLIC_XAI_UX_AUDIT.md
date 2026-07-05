# Session 78 - Public XAI Labels And UX Audit

Date: 2026-07-06

## What Changed

- Public forecast factors no longer expose LightGBM internal names such as `Column_17`.
- Added Korean judgment labels/messages for public prediction factors:
  - `공급·출하 압력`
  - `계절 수요 구간`
  - `기상·재해 변수`
  - known engineered features such as recent price trend, weather pressure, market volume, and event demand.
- `/api/v1/items/{item_code}/forecast` now returns public factor labels in `top_factors`.
- `/api/v1/items/{item_code}/forecast/explanation` now builds reason messages from the same public factor dictionary.
- Added regression coverage so internal `Column_*` factors cannot leak back into forecast/explanation payloads.
- Changed top navigation copy from `가격 예측 설명` to `예측 판단`.
- Reworked the top prediction panel and statistics panel so they show judgment text first instead of feature-description copy.
- Removed major `읽는 법`, `점수 해석`, and `산출 기준` explanation blocks from the risk panel.
- Risk panel now summarizes the current strongest risk factor instead of explaining how to read the widget.
- Created a 100-piece UX/function audit tracker at `docs/UX_FUNCTION_AUDIT_100.md`.

## Verification

- `python -m pytest tests\test_api.py tests\test_pipeline.py -q`
  - Result: 51 passed, 1 warning.
- Local FastAPI:
  - `http://127.0.0.1:8010/health`
  - Result: `{"status":"ok","version":"0.3.0","env":"development","scheduler":true}`
- In-app browser local UI:
  - Loaded `http://127.0.0.1:8010/?v=local-audit`
  - Console errors: none.
  - Top nav labels confirmed: `실시간 지도`, `예측 판단`, `통계`.
  - Old top-panel explanation strings not present.
  - `예측 판단` panel showed `현재 판단` and `AI 총평`.
  - `통계` panel showed `오늘 판단`.

## Current Known Gaps

1. Lower map-level hover popups still need another direct coordinate reproduction pass.
2. FarmMap land-use colors need a visible legend and overlap pattern when crop region color is also active.
3. Long horizons such as 6-month/1-year need accuracy gating before prominent display.
4. Cultivation/market tab should be rebuilt around monthly shipment, regional shipment rank, national share, and market influence.
5. More page copy should continue moving from feature explanation to judgment text.

## Working Style To Continue

- Treat trust issues first: any fake-looking number, internal label, or inconsistent price should be fixed before adding new decoration.
- Keep public UI and API language farmer-readable and Korean-first.
- Prefer real data, cached source data, or clearly marked model output. Do not create arbitrary placeholder numbers.
- After each feature slice, update `docs/UX_FUNCTION_AUDIT_100.md`.
- Run targeted tests first, then smoke/browser checks when frontend or public API behavior changes.
