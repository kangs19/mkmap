# MK-MAP Meta and Feature Engine Spec

## Goal

Build item-level metadata and feature engines for agricultural price risk signals.
The engine should explain each crop through production regions, market movement,
weather stress, disaster events, and forecast confidence.

## Target Items

- cabbage: 배추
- radish: 무
- onion: 양파
- green_onion: 대파
- garlic: 마늘

## Engine Layers

### 1. Item Meta Engine

Static and semi-static crop metadata.

- item_code
- item_name
- category
- storage_type
- price_volatility
- import_dependency
- weather_sensitivity
- growth_calendar
- demand_events
- substitute_items
- main_markets
- metadata_confidence

Primary sources:

- Internal crop taxonomy
- KOSIS production statistics
- KAMIS item/market metadata

### 2. Production Region Engine

Regional production concentration and map weights.

- main_province
- main_city_county
- production_volume
- cultivation_area
- production_share
- region_weight
- seasonality

Primary sources:

- KOSIS
- public region boundary GeoJSON
- manual crop-region override table

### 3. Price Market Engine

Price trend and market movement features.

- retail_price
- wholesale_price
- market_settlement_price
- price_change_1d
- price_change_7d
- price_change_14d
- price_volatility_30d
- abnormal_price_spike
- market_volume_signal

Primary sources:

- KAMIS regional item retail/wholesale price API
- aT public wholesale market settlement API

### 4. Agri Weather Engine

Crop-region weather stress features.

- temperature
- rainfall
- humidity
- wind_speed
- sunshine
- soil_or_agri_observed_features
- crop_weather_stress_score
- heat_stress
- cold_stress
- heavy_rain_stress
- drought_stress

Primary sources:

- KMA crop main-production-area detailed weather API
- RDA agricultural weather observation API

### 5. Disaster Event Engine

Event-level risk overlays.

- weather_alerts
- impact_forecast_heatwave
- impact_forecast_coldwave
- typhoon_distance
- typhoon_expected_impact
- special_warning_level
- event_risk_score

Primary sources:

- KMA weather alert API
- KMA impact forecast API
- KMA typhoon API

### 6. Forecast Context Engine

Forward-looking weather context.

- short_or_midterm_temperature_outlook
- precipitation_outlook
- wind_outlook
- synoptic_context
- satellite_context
- forecast_risk_modifier

Primary sources:

- KMA midterm forecast API
- KMA weather chart API
- KMA satellite image API

### 7. Risk Signal Engine

Final item-region risk score.

- supply_shock
- demand_pressure
- weather_pressure
- market_pressure
- event_pressure
- risk_score
- risk_level
- price_effect
- top_factors
- natural_language_summary
- confidence

Suggested scoring:

- market_pressure: 35%
- weather_pressure: 25%
- production_region_weight: 15%
- disaster_event_pressure: 15%
- forecast_context: 10%

## API Key Mapping

- DATA_GO_KR_API_KEY: data.go.kr shared key
- KOSIS_API_KEY: KOSIS key
- KAMIS_API_KEY: KAMIS key

Do not commit real API keys.

## Build Order

1. Item Meta Engine
2. Production Region Engine
3. Price Market Engine
4. Agri Weather Engine
5. Disaster Event Engine
6. Risk Signal Engine
7. Forecast Context Engine

## First Deliverable

Generate one metadata document per item:

- item profile
- main production regions
- growth and harvest calendar
- weather sensitivity
- price volatility profile
- available API source coverage
- missing data notes

## Repository Structure

- `metadata/schema/item_meta.schema.json`
  JSON Schema for item metadata.
- `metadata/items/*.json`
  One metadata file per crop item.
- `mkmap_meta/registry.py`
  Loads metadata and derives feature-engine plans.
- `mkmap_meta/models.py`
  Normalized feature dataclasses consumed by engines.
- `mkmap_meta/connectors/`
  External API connector interfaces and implementations.
- `mkmap_meta/pipeline.py`
  Aggregates connector outputs into item feature bundles.
- `scripts/show_engine_plans.py`
  Prints generated engine plans for all items.
- `scripts/build_feature_bundles.py`
  Prints normalized feature bundles. Uses configured connectors when env vars exist.
- `scripts/export_signals.py`
  Prints API-facing risk signal responses.
- `docs/FASTAPI_INTEGRATION.md`
  Example FastAPI router and response contract.

## How to Add a New Item

1. Add `metadata/items/{item_code}.json`.
2. Fill crop, production, market, weather, event, and source profiles.
3. Set `feature_engine_profile.engine_set`.
4. Add item-specific `feature_overrides` only when default engine behavior is not enough.
5. Run:

```powershell
python scripts/show_engine_plans.py
```

If the item appears in the generated plan, the API connectors and risk engine can
consume it without adding item-specific code.

## Extension Rules

- Prefer metadata changes over code changes.
- Add a new engine only when multiple items need a new feature family.
- Add `feature_overrides` when one item needs a different weight, lag, or event behavior.
- Keep raw API fields inside source connectors. Engine inputs should use normalized names.
- Keep manual production-region weights until KOSIS mapping is verified.

## Price Connector Environment

The first connector layer supports KAMIS and aT regional price data through
environment variables. Actual API URLs must be copied from the official service
detail pages.

```env
KAMIS_API_KEY=
KAMIS_PRICE_BASE_URL=
KAMIS_KEY_PARAM=serviceKey
KAMIS_DATE_PARAM=date
KAMIS_ITEM_PARAM=item_code

DATA_GO_KR_API_KEY=
AT_REGIONAL_PRICE_BASE_URL=
AT_REGIONAL_PRICE_OPERATION=
AT_REGIONAL_PRICE_DATE_PARAM=date
AT_REGIONAL_PRICE_ITEM_PARAM=item_code
```

If these URLs are not configured, the pipeline still builds item metadata and
engine plans but returns empty price features.

## Production Connector Behavior

Production features are loaded in two layers:

1. `KosisProductionConnector` when KOSIS table URL and table IDs are configured.
2. `ManualProductionConnector` as a fallback from each item's
   `production_profile.manual_regions`.

This means the engine can produce map weights before KOSIS mapping is finalized.
Once KOSIS mappings are verified, manual weights remain useful as guardrails and
review hints.

## Weather Connector Behavior

Weather features are normalized into `WeatherFeature` from:

- KMA crop main-production-area detailed weather
- RDA agricultural weather observation

The first-pass `score_weather_stress` helper combines normalized weather values
with each item's `weather_profile.sensitivity`. This keeps crop-specific
behavior in metadata:

- cabbage can react strongly to heat and heavy rain.
- green onion can react strongly to cold and wind.
- onion and garlic can reduce direct weather shock through storage behavior.

The thresholds are intentionally transparent defaults and should be calibrated
after real observations and price outcomes are collected.

## Event Connector Behavior

Event features are normalized into `EventFeature` from:

- KMA weather alert
- KMA impact forecast
- KMA typhoon information
- KMA midterm forecast

The first-pass `score_event_stress` helper maps advisory/warning levels and
explicit API severity fields to a normalized score, then applies each item's
`event_profile.event_weights`.

Event APIs should be used as overlays. They do not replace measured weather or
market data; they raise confidence that a weather shock may become a supply
shock for sensitive crops and production regions.

## Risk Signal Engine

The first-pass risk engine combines:

- market pressure from recent price movement
- production-region weight from KOSIS or manual fallback
- weather pressure from crop-specific weather stress
- disaster event pressure from alerts, impact forecasts, typhoon, and midterm forecasts

Output per item-region:

- risk_score: 0-1
- risk_level: normal, watch, warning, critical
- price_effect: stable, upward_pressure, strong_upward_pressure
- top_factors
- natural-language summary

This rule-based engine is intentionally transparent. Later LightGBM or other ML
models can replace individual pressure components while preserving the same
output schema.

## Feature Override Examples

Storage crops such as onion and garlic can reduce direct weather shock impact:

```json
{
  "risk_signal": {
    "market_pressure_weight": 0.42,
    "storage_buffer": true
  }
}
```

Fresh and highly weather-sensitive crops such as cabbage can increase weather
pressure:

```json
{
  "risk_signal": {
    "weather_pressure_weight": 0.3,
    "event_pressure_weight": 0.18
  }
}
```
