from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from mkmap_meta.engines.event_stress import score_event_stress
from mkmap_meta.engines.weather_stress import score_weather_stress
from mkmap_meta.models import EventFeature, ItemFeatureBundle, PriceFeature, ProductionFeature, WeatherFeature


@dataclass(frozen=True)
class TopFactor:
    factor: str
    contribution: float
    direction: str


@dataclass(frozen=True)
class RegionRiskSignal:
    item_code: str
    region_code: str
    region_name: str
    risk_score: float
    risk_level: str
    price_effect: str
    top_factors: list[TopFactor] = field(default_factory=list)
    summary: str = ""


def build_region_risk_signals(bundle: ItemFeatureBundle) -> list[RegionRiskSignal]:
    item = bundle.metadata["item"]
    plan = bundle.metadata["engine_plan"]
    risk_weights = plan["risk_weights"]
    weather_sensitivity = item["weather_profile"]["sensitivity"]
    event_weights = item["event_profile"]["event_weights"]

    production_by_region = _production_by_region(bundle.production)
    weather_by_region = _weather_by_region(bundle.weather)
    events_by_region = _events_by_region(bundle.events)
    market_pressure = _market_pressure(bundle.prices)

    signals: list[RegionRiskSignal] = []
    for region_code, production in production_by_region.items():
        weather_pressure = _weather_pressure(weather_by_region.get(region_code, []), weather_sensitivity)
        event_pressure = _event_pressure(events_by_region.get(region_code, []) + events_by_region.get("*", []), event_weights)
        production_pressure = production.production_share or 0.0

        factors = {
            "market_pressure": market_pressure * risk_weights.get("market_pressure", 0.0),
            "weather_pressure": weather_pressure * risk_weights.get("weather_pressure", 0.0),
            "production_region_weight": production_pressure * risk_weights.get("production_region_weight", 0.0),
            "disaster_event_pressure": event_pressure * risk_weights.get("disaster_event_pressure", 0.0),
            "forecast_context": event_pressure * risk_weights.get("forecast_context", 0.0),
        }

        if risk_weights.get("storage_buffer"):
            factors["weather_pressure"] *= 0.75
            factors["disaster_event_pressure"] *= 0.8

        risk_score = min(1.0, sum(factors.values()))
        top_factors = [
            TopFactor(factor=name, contribution=round(value, 4), direction="up")
            for name, value in sorted(factors.items(), key=lambda pair: pair[1], reverse=True)
            if value > 0
        ][:3]

        risk_level = _risk_level(risk_score)
        price_effect = _price_effect(risk_score, market_pressure, weather_pressure, event_pressure)
        signals.append(
            RegionRiskSignal(
                item_code=bundle.item_code,
                region_code=region_code,
                region_name=production.region_name,
                risk_score=round(risk_score, 4),
                risk_level=risk_level,
                price_effect=price_effect,
                top_factors=top_factors,
                summary=_summary(item["item_name"], production.region_name, risk_level, price_effect, top_factors),
            )
        )

    return sorted(signals, key=lambda signal: signal.risk_score, reverse=True)


def _production_by_region(production: list[ProductionFeature]) -> dict[str, ProductionFeature]:
    return {feature.region_code: feature for feature in production if feature.region_code}


def _weather_by_region(weather: list[WeatherFeature]) -> dict[str, list[WeatherFeature]]:
    grouped: dict[str, list[WeatherFeature]] = {}
    for feature in weather:
        grouped.setdefault(feature.region_code, []).append(feature)
    return grouped


def _events_by_region(events: list[EventFeature]) -> dict[str, list[EventFeature]]:
    grouped: dict[str, list[EventFeature]] = {}
    for feature in events:
        grouped.setdefault(feature.region_code or "*", []).append(feature)
    return grouped


def _weather_pressure(weather: list[WeatherFeature], sensitivity: dict[str, float]) -> float:
    if not weather:
        return 0.0
    return max(score_weather_stress(feature, sensitivity).stress_score for feature in weather)


def _event_pressure(events: list[EventFeature], event_weights: dict[str, float]) -> float:
    if not events:
        return 0.0
    return max(score_event_stress(feature, event_weights).stress_score for feature in events)


def _market_pressure(prices: list[PriceFeature]) -> float:
    if len(prices) < 2:
        return 0.0

    sorted_prices = sorted(prices, key=lambda feature: feature.base_date, reverse=True)
    latest = _representative_price(sorted_prices[0])
    previous_values = [_representative_price(feature) for feature in sorted_prices[1:8]]
    previous_values = [value for value in previous_values if value is not None]
    if latest is None or not previous_values:
        return 0.0

    baseline = mean(previous_values)
    if baseline <= 0:
        return 0.0

    change_rate = (latest - baseline) / baseline
    return max(0.0, min(1.0, change_rate / 0.35))


def _representative_price(feature: PriceFeature) -> float | None:
    return feature.wholesale_price or feature.retail_price or feature.settlement_price


def _risk_level(score: float) -> str:
    if score >= 0.7:
        return "critical"
    if score >= 0.45:
        return "warning"
    if score >= 0.25:
        return "watch"
    return "normal"


def _price_effect(score: float, market: float, weather: float, event: float) -> str:
    if score < 0.25:
        return "stable"
    if max(market, weather, event) >= 0.6:
        return "strong_upward_pressure"
    return "upward_pressure"


def _summary(item_name: str, region_name: str, risk_level: str, price_effect: str, top_factors: list[TopFactor]) -> str:
    factor_text = ", ".join(factor.factor for factor in top_factors) or "주요 요인 없음"
    return f"{region_name} {item_name} 위험도는 {risk_level}이며, 가격 영향은 {price_effect}입니다. 주요 요인은 {factor_text}입니다."
