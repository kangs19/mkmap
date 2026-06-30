# FastAPI Integration

This module is designed so the deployed API server can call the metadata,
service-catalog, and signal engines without item-specific branching.

## Example Router

The repository includes a drop-in router:

```python
from fastapi import FastAPI
from mkmap_meta.api import create_signal_router

app = FastAPI()
app.include_router(create_signal_router())
```

Or, for a standalone app:

```python
from mkmap_meta.api import create_app

app = create_app()
```

## Response Shape

`GET /api/v1/items/cabbage/signals`

```json
{
  "item_code": "cabbage",
  "item_name": "배추",
  "base_date": "2026-06-29",
  "signals": [
    {
      "item_code": "cabbage",
      "region_code": "42",
      "region_name": "강원",
      "risk_score": 0.6744,
      "risk_level": "warning",
      "price_effect": "strong_upward_pressure",
      "top_factors": [
        {
          "factor": "market_pressure",
          "contribution": 0.3091,
          "direction": "up"
        }
      ],
      "summary": "강원 배추 위험도는 warning이며, 가격 영향은 strong_upward_pressure입니다."
    }
  ],
  "data_status": {
    "price_features": 7,
    "production_features": 3,
    "weather_features": 3,
    "event_features": 2,
    "has_price_data": true,
    "has_weather_data": true,
    "has_event_data": true
  }
}
```

`GET /api/v1/api-services`

```json
{
  "summary": {
    "total_services": 12,
    "configured_services": 0,
    "missing_required_services": 10,
    "by_provider": {
      "data_go_kr": 10,
      "kamis": 1,
      "kosis": 1
    },
    "by_engine_role": {
      "agri_weather": {
        "total": 2,
        "configured": 0
      }
    }
  },
  "services": []
}
```

The endpoint reports missing environment variable names, but never returns
secret values.

## Environment

Use `.env.example` as the source of truth. Real API keys should live only in the
deployment environment, not in source control.

Required for full live signals:

- `KAMIS_API_KEY`
- `KAMIS_PRICE_BASE_URL`
- `DATA_GO_KR_API_KEY`
- `AT_REGIONAL_PRICE_BASE_URL`
- `AT_MARKET_SETTLEMENT_BASE_URL`
- `KOSIS_API_KEY`
- `KOSIS_PRODUCTION_BASE_URL`
- `KOSIS_PRODUCTION_ORG_ID`
- `KOSIS_PRODUCTION_TBL_ID`
- `KMA_CROP_WEATHER_BASE_URL`
- `RDA_AGRI_WEATHER_BASE_URL`
- `KMA_WEATHER_ALERT_BASE_URL`
- `KMA_IMPACT_FORECAST_BASE_URL`
- `KMA_TYPHOON_BASE_URL`
- `KMA_MIDTERM_FORECAST_BASE_URL`

Optional after the core flow is stable:

- `KMA_SATELLITE_BASE_URL`
- `KMA_WEATHER_CHART_BASE_URL`

When a connector is not configured, the service still returns region signals
using available metadata and sets `data_status` counts to zero for missing
feature families.

## Local Checks

```powershell
python scripts/validate_metadata.py
python scripts/show_api_services.py
python scripts/validate_api_catalog.py
python scripts/preview_api_requests.py
python scripts/smoke_api_services.py
python scripts/export_signals.py --item cabbage --date 2026-06-29
python scripts/export_signals.py --date 2026-06-29
python scripts/smoke_api_contract.py
```

## Added Endpoints

- `GET /api/v1/items/{item_code}/signals`
- `GET /api/v1/items/{item_code}/forecast`
- `GET /api/v1/items/{item_code}/forecast/explanation`
- `GET /api/v1/signals/today`
- `GET /api/v1/items/{item_code}/meta-engine`
- `GET /api/v1/api-services`

`GET /api/v1/items/{item_code}/forecast` includes `model_version` and
`model_scope`. `model_scope` is `item` when an accepted item-specific model was
used and `global` when the global fallback model was used.

`GET /api/v1/items/{item_code}/forecast/explanation` returns a public-facing
Korean explanation payload with a headline, model scope label, confidence label,
forecast probability labels, reason messages, top risk regions, and data
freshness for price, region signal, and forecast data.

The `meta-engine` endpoint is useful for admin/debug pages because it shows
which engines, source coverage, risk weights, and weather factors are active for
the item.

The `api-services` endpoint is useful for admin/debug pages because it shows
which approved external APIs are mapped to each engine role and which
environment variables are still missing.
