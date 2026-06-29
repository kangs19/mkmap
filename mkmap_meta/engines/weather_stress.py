from __future__ import annotations

from dataclasses import dataclass

from mkmap_meta.models import WeatherFeature


@dataclass(frozen=True)
class WeatherStressResult:
    region_code: str
    stress_score: float
    factors: dict[str, float]


def score_weather_stress(weather: WeatherFeature, sensitivity: dict[str, float]) -> WeatherStressResult:
    """Simple first-pass crop weather stress score.

    This intentionally stays transparent. Thresholds are conservative defaults
    and can later move to metadata or model calibration.
    """

    factors: dict[str, float] = {}

    if weather.temperature is not None:
        heat = max(0.0, min(1.0, (weather.temperature - 28.0) / 8.0))
        cold = max(0.0, min(1.0, (5.0 - weather.temperature) / 10.0))
        factors["heat"] = heat * sensitivity.get("heat", 0.0)
        factors["cold"] = cold * sensitivity.get("cold", 0.0)

    if weather.rainfall is not None:
        heavy_rain = max(0.0, min(1.0, weather.rainfall / 80.0))
        drought = max(0.0, min(1.0, (1.0 - weather.rainfall) / 1.0))
        factors["heavy_rain"] = heavy_rain * sensitivity.get("heavy_rain", 0.0)
        factors["drought"] = drought * sensitivity.get("drought", 0.0)

    if weather.wind_speed is not None:
        wind = max(0.0, min(1.0, (weather.wind_speed - 8.0) / 12.0))
        factors["wind"] = wind * sensitivity.get("wind", 0.0)

    if weather.humidity is not None:
        humidity = max(0.0, min(1.0, (weather.humidity - 80.0) / 20.0))
        factors["humidity"] = humidity * sensitivity.get("humidity", 0.0)

    score = max(factors.values(), default=0.0)
    return WeatherStressResult(
        region_code=weather.region_code,
        stress_score=round(score, 4),
        factors={key: round(value, 4) for key, value in factors.items()},
    )

