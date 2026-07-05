# UI Numeric Source Audit

Updated: 2026-07-05 KST

Purpose: every number shown on `mk-map.com` must be either externally sourced, model-derived from sourced data, or explicitly hidden as unavailable. Arbitrary UI fallback values must not be displayed as data.

## Verified Production API Sources

Checked against `https://mk-map.com` on 2026-07-05:

| Endpoint | Status | What It Provides | Source Class |
|---|---:|---|---|
| `/api/v1/signals/today` | 200 | item forecast probability, risk score, confidence, hotspot region | model output from stored price/weather/region features |
| `/api/v1/dashboard/cards` | 200 | compact dashboard cards | DB forecasts, region signals, daily prices |
| `/api/v1/map/prices?item_code=cabbage` | 200 | daily item price history | KAMIS `daily_prices` |
| `/api/v1/map/regional-prices?item_code=cabbage` | 200 | market/sido wholesale and retail price | MAFRA/agromarket auction data, derived retail where API provides it |
| `/api/v1/map/weather` | 200 | regional weather summary | KMA/RDA weather rows in `daily_weather` |
| `/api/v1/drought` | 200 | reservoir/rainfall drought summary | MAFRA 669 |

## UI Number Inventory

| UI Area | Number Shown | Current Source | Status | Notes |
|---|---|---|---|---|
| Header date | today date | browser system date | OK | Not external data. |
| Header weather | avg temp, alert count | `/api/v1/map/weather` | fixed | Removed previous hardcoded sunny text. If API fails, shows unavailable text instead of fake weather. |
| Data status pill | base date | `/api/v1/signals/today.base_date` | OK | DB/model freshness indicator. |
| Left mini cards | risk labels and forecast state | `/api/v1/signals/today` | fixed | No longer uses `ITEMS` fallback risk/probability numbers. |
| Dashboard counts | forecast count, price count | `LIVE_ITEMS`, `LIVE_NATIONAL_PRICES`, preferably `/dashboard/cards` | OK | Counts reflect loaded API payloads. |
| Dashboard item cards | price, risk score, up probability | `/api/v1/map/prices`, `/api/v1/signals/today` | fixed | If no API value exists, displays `—` or collection status. |
| Map fill, production mode | production weight, area, ton | `/static/city_agri_data.json` generated from KOSIS-based static seed | partial | Static seed is acceptable for map geography, but not live verified at request time. Needs eventual DB-backed `/map/production` replacement. |
| Map fill, price mode | regional vs national price change | `/api/v1/map/regional-prices`; fallback to KAMIS national only in wholesale mode | fixed | Removed retail 1.35 multiplier fallback. |
| Map fill, risk mode | risk score | region signal or static derived score from production/price index | partial | Derived score, not raw public API field. Must be labeled as model/derived. |
| Map pins | price by region, forecast change | regional prices + `periodForecastPct()` from sourced price delta and model probability | partial | Forecast is model-derived; if model probability missing, AI component contributes 0 instead of fake 50%. |
| Hover card price | current and predicted price | `getRegionPriceContext()` from regional/national API prices | fixed | Hover and right detail use same price context. |
| Hover card production share | shipment share or production share | `/api/v1/map/shipment-share` if loaded; otherwise KOSIS production share from static seed | partial | Label distinguishes shipment share vs production estimate. |
| Right forecast price | selected horizon predicted price | current price + period forecast formula | derived | Formula is transparent but still model output, not raw API. |
| Right period trend reasons | forecast conclusion plus grouped up/down/neutral reasons | `/api/v1/items/{item}/forecast/explanation` | fixed | UI now shows a decision card first, then separates 상승 압력, 하락 압력, 확인할 변수 so mixed reasons are not read as a contradiction. |
| Right confidence | confidence label | `/api/v1/signals/today.confidence` | fixed | Removed arbitrary `85% - period` calculation. |
| Right chart history | historical prices | `/api/v1/map/prices` | OK | Removed previous random/sample chart fallback in earlier work. |
| Right chart forecast band | future curve | model probability + latest KAMIS price | partial | If probability is unavailable, curve stays neutral instead of fabricated direction. |
| Cultivation tab | area, volume, season, region rank | static KOSIS-based city seed | partial | Good enough for first map context; must be regenerated from DB-backed KOSIS for production-grade claims. |
| Market tab | market, wholesale/retail price | `/api/v1/map/regional-prices` and market influence mapping | partial | Market coordinates/influence mapping are static reference data; exact influence should be improved from auction flow data. |
| Drought/Weather layers | reservoir, rainfall, temp, alerts | `/api/v1/drought`, `/api/v1/map/weather` | OK/partial | Weather rows can lag by provider availability. |

## Fixed In This Audit

- Disabled inline `CITY_DATA` fallback display when `/static/city_agri_data.json` fails.
- Cleared old inline city seed before loading static city data, so hidden old Claude-style constants cannot leak into the map.
- Replaced header hardcoded weather text with `/api/v1/map/weather` summary.
- Removed dashboard and default briefing fallback to `ITEMS.risk_score` / `ITEMS.up_prob`.
- Removed arbitrary detail confidence percentage formula.
- Removed retail fallback multiplier `wholesale * 1.35`.
- Changed missing forecast probability handling from fake `0.5` to neutral/no-value display.

## Data That Still Needs Stronger Source Work

| Data | Current State | Can We Create It? | Next Action |
|---|---|---:|---|
| city-level current production/harvest rate | static seed only | yes | Build DB-backed `/api/v1/map/production` from KOSIS collection results and replace static file use. |
| exact market influence per region | static nearest/representative mapping | yes | Use agromarket auction flow by origin/market to compute dominant market per crop-region. |
| retail price when regional retail is missing | now hidden | yes | Wire MAFRA retail price API 163 or KAMIS retail source by item/region. Do not estimate by multiplier. |
| import/substitute supply volume | unavailable in UI | maybe | Need separate import/statistics API or customs data. Keep hidden until sourced. |
| pest, disease, soil, FarmMap parcel features | not wired | yes/partial | Validate FarmMap/API coverage first, then add feature tables. |
| KMA weather alert/satellite provider failures | known intermittent/permission issue | partial | Retry diagnostics and mark provider error separately from no-data. |
| city-level daily weather matched to each crop region | coarse crop/region rows | yes | Backfill ASOS/AWS/KMA crop-weather mapping for each production region. |

## Rule For Future UI Work

If a number cannot be traced to an endpoint, DB table, static reference file with documented provenance, or a named model formula, do not show it. Render `—`, `수집 중`, or `미연동` instead.
