# Session 86 - Readiness UX Copy And API Summary (2026-07-06)

## Purpose

Continue from Session 85 by making readiness filtering understandable to users.

The model artifacts now know which item/horizon forecasts are held out. This session exposed that judgment through the backend and connected it to the frontend copy.

## Backend Changes

Updated `backend/app/services/horizon_forecasts.py`.

The public forecast and explanation responses now include a compact `readiness` object:

- `status`
- `item_status`
- `item_score`
- `active_horizons`
- `hidden_horizons`
- `hidden_details`
- `message`

Each hidden horizon receives a user-facing Korean message.

Examples:

- `1개월은 과거 검증에서 상승·하락 방향이 불안정해 공개 예측에서 제외했습니다.`
- `6개월 장기 예측은 충분한 검증이 쌓인 뒤 공개합니다.`
- `현재 이 품목은 공개 예측에 쓰기에는 검증이 부족합니다. 실측 가격과 지역 정보 위주로 확인하세요.`

The backend still keeps technical reasons such as `low_backtest_direction` internally, but public responses now have readable judgment text.

## Frontend Changes

Updated `index.html`.

- Stores `forecast.readiness` in `LIVE_HORIZON_READINESS`.
- `horizonPolicyText()` now prefers the backend readiness message.
- Hidden/held horizons are counted from rows with `held_out` or `available === false`, not only long horizons.
- The explanation panel now labels unavailable periods as `검증 대기`.
- Period rows show a short judgment message instead of generic `데이터 부족`.
- The detail-panel notice title changed from `장기 예측 판단` to `예측 공개 판단`.
- Added `topicName()` so crop names use natural Korean topic particles, for example `배추는` instead of `배추은`.

## Browser Check

Opened the local app through a temporary localhost server:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Browser check:

- Page loaded.
- Main layout rendered.
- `예측 판단` panel opened.
- The panel no longer showed the bad particle `배추은`.
- It displayed `배추는 아직 기간별 예측 근거가 약해...`.

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

## Next Work

1. Use `readiness.hidden_details` in the period button UI.
   - Disabled period buttons should explain why a period is unavailable.

2. Add a compact readiness badge near the forecast tab.
   - Good labels: `공개 가능`, `검증 대기`, `실측 우선`.

3. Convert remaining technical or stale explanatory copy into judgment copy.
   - Avoid feature explanations.
   - Prefer “지금은 이렇게 판단합니다” language.

4. Continue improving held crops through KOSIS, KMA, and FarmMap mappings.

