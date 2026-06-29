from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.weather import normalize_weather_rows
from mkmap_meta.engines.weather_stress import score_weather_stress
from mkmap_meta.registry import default_registry


def main() -> None:
    sample_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "item_code": "cabbage",
                            "region_code": "42",
                            "date": "20260629",
                            "temperature": "31.5",
                            "rainfall": "72",
                            "humidity": "86",
                            "wind_speed": "5.2",
                            "sunshine": "3.1"
                        }
                    ]
                }
            }
        }
    }
    weather = normalize_weather_rows(
        sample_payload,
        item_code="cabbage",
        default_date=date(2026, 6, 29),
        source="sample_weather",
    )
    item = default_registry().get_item("cabbage")
    stress = [
        asdict(score_weather_stress(feature, item["weather_profile"]["sensitivity"]))
        for feature in weather
    ]
    print(json.dumps({"weather": [asdict(feature) for feature in weather], "stress": stress}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
