from __future__ import annotations

import os

from mkmap_meta.connectors.price import AtMarketSettlementConnector, AtRegionalPriceConnector, KamisPriceConnector
from mkmap_meta.connectors.production import KosisProductionConnector, ManualProductionConnector
from mkmap_meta.connectors.events import (
    ImpactForecastConnector,
    MidtermForecastConnector,
    SatelliteConnector,
    TyphoonConnector,
    WeatherAlertConnector,
    WeatherChartConnector,
)
from mkmap_meta.connectors.weather import CropMainAreaWeatherConnector, RdaAgriWeatherConnector
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.pipeline import ItemFeaturePipeline


def build_default_pipeline() -> ItemFeaturePipeline:
    ensure_env_loaded()

    price_connectors = []

    if os.getenv("KAMIS_API_KEY"):
        price_connectors.append(KamisPriceConnector())

    if os.getenv("DATA_GO_KR_API_KEY"):
        price_connectors.append(AtRegionalPriceConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        price_connectors.append(AtMarketSettlementConnector())

    production_connectors = []
    if os.getenv("KOSIS_PRODUCTION_BASE_URL") and os.getenv("KOSIS_API_KEY"):
        production_connectors.append(KosisProductionConnector())
    production_connectors.append(ManualProductionConnector())

    weather_connectors = []
    if os.getenv("DATA_GO_KR_API_KEY"):
        weather_connectors.append(CropMainAreaWeatherConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        weather_connectors.append(RdaAgriWeatherConnector())

    event_connectors = []
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(WeatherAlertConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(ImpactForecastConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(TyphoonConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(MidtermForecastConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(SatelliteConnector())
    if os.getenv("DATA_GO_KR_API_KEY"):
        event_connectors.append(WeatherChartConnector())

    return ItemFeaturePipeline(
        price_connectors=price_connectors,
        production_connectors=production_connectors,
        weather_connectors=weather_connectors,
        event_connectors=event_connectors,
    )
