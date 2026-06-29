from __future__ import annotations

from dataclasses import dataclass

from mkmap_meta.models import EventFeature


@dataclass(frozen=True)
class EventStressResult:
    event_type: str
    region_code: str | None
    stress_score: float
    reason: str


LEVEL_SCORES = {
    "관심": 0.2,
    "주의": 0.45,
    "주의보": 0.55,
    "경계": 0.7,
    "경보": 0.85,
    "심각": 1.0,
    "advisory": 0.55,
    "warning": 0.85,
}


EVENT_BASE_SCORES = {
    "weather_alert": 0.65,
    "impact_forecast": 0.55,
    "typhoon": 0.8,
    "midterm_forecast": 0.35,
}


def score_event_stress(event: EventFeature, event_weights: dict[str, float]) -> EventStressResult:
    if event.severity_score is not None:
        base_score = max(0.0, min(1.0, event.severity_score))
        reason = "explicit severity_score"
    elif event.level:
        base_score = LEVEL_SCORES.get(event.level.lower(), LEVEL_SCORES.get(event.level, 0.5))
        reason = f"level={event.level}"
    elif event.event_type == "midterm_forecast" and _mentions_rain_or_typhoon(event):
        base_score = 0.55
        reason = "forecast mentions rain or typhoon"
    else:
        base_score = EVENT_BASE_SCORES.get(event.event_type, 0.3)
        reason = "event default"

    weight = event_weights.get(event.event_type, 0.0)
    return EventStressResult(
        event_type=event.event_type,
        region_code=event.region_code,
        stress_score=round(base_score * weight, 4),
        reason=reason,
    )


def _mentions_rain_or_typhoon(event: EventFeature) -> bool:
    text = " ".join(str(value or "") for value in (event.title, event.description, event.raw.get("wfSv")))
    return any(keyword in text for keyword in ("비", "강수", "태풍", "열대", "호우"))

