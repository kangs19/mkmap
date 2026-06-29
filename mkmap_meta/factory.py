from __future__ import annotations

import os

from mkmap_meta.connectors.price import AtRegionalPriceConnector, KamisPriceConnector
from mkmap_meta.connectors.production import KosisProductionConnector, ManualProductionConnector
from mkmap_meta.connectors.events import ImpactForecastConnector, MidtermForecastConnector, TyphoonConnector, WeatherAlertConnector
from mkmap_meta.connectors.weather import CropMainAreaWeatherConnector, RdaAgriWeatherConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.pipeline import ItemFeaturePipeline


def build_default_pipeline() -> ItemFeaturePipeline:
    ensure_env_loaded()

    price_connectors = []

    if os.getenv("KAMIS_API_KEY"):
        price_connectors.append(KamisPriceConnector())

    if os.getenv("AT_REGIONAL_PRICE_BASE_URL") and os.getenv("DATA_GO_KR_API_KEY"):
        price_connectors.append(AtRegionalPriceConnector())

    production_connectors = []
    if os.getenv("KOSIS_PRODUCTION_BASE_URL") and os.getenv("KOSIS_API_KEY"):
        production_connectors.append(KosisProductionConnector())
    production_connectors.append(ManualProductionConnector())

    weather_connectors = []
    if os.getenv("DATA_GO_KR_API_KEY"):
        weather_connectors.append(CropMainAreaWeatherConnector())
    if os.getenv("RDA_AGRI_WEATHER_BASE_URL") and os.getenv("DATA_GO_KR_API_KEY"):
        weather_connectors.append(RdaAgriWeatherConnector())

    event_connectors = []
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(WeatherAlertConnector())
    if os.getenv("KMA_IMPACT_FORECAST_BASE_URL") and os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(ImpactForecastConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(TyphoonConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(MidtermForecastConnector())

    return ItemFeaturePipeline(
        price_connectors=price_connectors,
        production_connectors=production_connectors,
        weather_connectors=weather_connectors,
        event_connectors=event_connectors,
    )
