from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"

REQUIRED_TOP_LEVEL = {
    "item_code",
    "item_name",
    "category",
    "crop_profile",
    "production_profile",
    "market_profile",
    "weather_profile",
    "event_profile",
    "feature_engine_profile",
    "source_coverage",
}

ALLOWED_ENGINES = {
    "item_meta",
    "production_region",
    "price_market",
    "agri_weather",
    "disaster_event",
    "forecast_context",
    "risk_signal",
}

ALLOWED_DATA_GO_KR_SERVICES = {
    "crop_weather",
    "agri_weather_observation",
    "weather_alert",
    "impact_forecast",
    "weather_chart",
    "satellite",
    "typhoon",
    "midterm_forecast",
    "at_regional_price",
    "at_settlement",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name}: invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def assert_keys(path: Path, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    if missing:
        errors.append(f"{path.name}: missing top-level keys: {', '.join(missing)}")
    return errors


def validate_item(path: Path, data: dict[str, Any]) -> list[str]:
    errors = assert_keys(path, data)
    if errors:
        return errors

    item_code = data["item_code"]
    if not path.stem == item_code:
        errors.append(f"{path.name}: filename must match item_code ({item_code}.json)")

    regions = data["production_profile"].get("manual_regions", [])
    if not regions:
        errors.append(f"{path.name}: production_profile.manual_regions must not be empty")
    weight_sum = sum(float(region.get("base_weight", 0)) for region in regions)
    if weight_sum <= 0:
        errors.append(f"{path.name}: production region weights must be greater than 0")
    if weight_sum > 1.05:
        errors.append(f"{path.name}: production region weights sum to {weight_sum:.2f}; expected <= 1.05")

    engines = set(data["feature_engine_profile"].get("engine_set", []))
    unknown_engines = sorted(engines - ALLOWED_ENGINES)
    if unknown_engines:
        errors.append(f"{path.name}: unknown engine(s): {', '.join(unknown_engines)}")
    if "risk_signal" not in engines:
        errors.append(f"{path.name}: engine_set should include risk_signal")

    weather_factors: set[str] = set()
    for window in data["weather_profile"].get("critical_windows", []):
        weather_factors.update(window.get("risk_factors", []))
    weather_sensitivity = set(data["weather_profile"].get("sensitivity", {}))
    missing_sensitivity = sorted(weather_factors - weather_sensitivity)
    if missing_sensitivity:
        errors.append(
            f"{path.name}: weather sensitivity missing factor(s): {', '.join(missing_sensitivity)}"
        )

    enabled_events = set(data["event_profile"].get("enabled_events", []))
    event_weights = set(data["event_profile"].get("event_weights", {}))
    missing_event_weights = sorted(enabled_events - event_weights)
    if missing_event_weights:
        errors.append(f"{path.name}: event weight missing for: {', '.join(missing_event_weights)}")

    coverage = data["source_coverage"]
    unknown_services = sorted(set(coverage.get("data_go_kr", [])) - ALLOWED_DATA_GO_KR_SERVICES)
    if unknown_services:
        errors.append(f"{path.name}: unknown data_go_kr service(s): {', '.join(unknown_services)}")

    return errors


def main() -> int:
    errors: list[str] = []
    seen_codes: set[str] = set()
    item_paths = sorted(ITEMS_DIR.glob("*.json"))

    if not item_paths:
        print(f"No item metadata files found under {ITEMS_DIR}")
        return 1

    for path in item_paths:
        try:
            data = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        item_code = data.get("item_code")
        if item_code in seen_codes:
            errors.append(f"{path.name}: duplicate item_code {item_code}")
        if item_code:
            seen_codes.add(item_code)

        errors.extend(validate_item(path, data))

    if errors:
        print("Metadata validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Metadata validation passed: {len(item_paths)} item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

