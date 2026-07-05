# Session 68 - Price Basis, Map Back Navigation, And Weather Layer UX (2026-07-05)

## User Problem

- Some crops such as cucumber may not have retail price data, which made price forecast display feel incomplete.
- The left `시세 표시` wholesale/retail choice was confusing because the map and forecasts should not disappear when retail is missing.
- Map back navigation from a city/county detail level did not visually return to the parent province on the first click.
- Weather markers were too subtle, and the UI did not explain whether weather values were today's data or the latest stored values.
- `재배 면적` and `가격 예측` checkboxes behaved like overlays, but they are actually map color modes.

## Decisions

- Use wholesale price as the primary map and forecast basis.
- Show retail only as secondary information when collected.
- Treat `재배 면적` and `가격 예측` as mutually exclusive map color modes.
- Keep weather and market locations as overlay marker layers.
- Weather values must be labeled as latest stored regional weather values from `/api/v1/map/weather`, not blindly "today".

## Implementation

Updated `index.html`.

- Replaced the wholesale/retail toggle with fixed `도매가 기준` copy.
- Added sidebar note: map colors and forecasts use wholesale; retail is shown only as secondary when available.
- Forced `getRegionPriceContext(...)` to use wholesale as primary.
- Removed retail mode from map color calculations.
- Made `재배 면적` and `가격 예측` mutually exclusive:
  - selecting one unchecks the other.
  - default is `가격 예측` on, `재배 면적` off.
- Added layer help text explaining:
  - production/price change map fill color.
  - weather/market are marker overlays.
- Fixed back navigation:
  - city/county detail back click now returns and fits to the parent province.
  - second back click returns to the national map.
- Improved weather layer:
  - added larger weather badges with condition icons.
  - condition icons are inferred from precipitation, heat/cold alerts, and temperature anomaly.
  - added bottom-left weather info control with `base_date`.
  - states clearly that this is latest stored weather, not guaranteed real-time today.

## Weather Data Note

`/api/v1/map/weather` returns the latest `DailyWeather` row per region.

- If daily KMA sync is current, the value can be today.
- If sync is delayed or local DB is empty, the UI should not claim today's weather.
- The current API does not expose full sky-condition categories, so icons are derived:
  - rain from precipitation/heavy-rain alert.
  - cold/snow-like state from cold alert or subzero temperature.
  - heat from heat alert or high temperature.
  - high/low temperature anomaly from `temp_anomaly`.

## Verification

- `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Static browser check at `http://127.0.0.1:8019/` showed:
  - fixed `도매가 기준` copy.
  - production/price mode help text.
  - no captured runtime errors.
  - production and price checkboxes are mutually exclusive.
- Local FastAPI check:
  - `/api/v1/map/weather` returned HTTP 200.
  - local DB response had `base_date:null` and empty `regions`, so weather markers could not be visually verified locally.

## Follow-Up

- Remove the older weather function declaration once `index.html` is split into smaller frontend modules.
- Add backend fields for sky condition if KMA short-term/ultra-short forecast sky codes are stored, so weather icons can represent actual clear/cloud/rain/snow rather than inferred categories.
