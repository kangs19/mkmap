from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.events import normalize_event_rows
from mkmap_meta.engines.event_stress import score_event_stress
from mkmap_meta.registry import default_registry


def main() -> None:
    sample_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "region_code": "42",
                            "date": "20260629",
                            "level": "경보",
                            "title": "호우경보",
                            "description": "강원 산지 강한 비"
                        },
                        {
                            "region_code": "46",
                            "date": "20260629",
                            "level": "주의보",
                            "title": "태풍 예비특보",
                            "description": "남해안 강풍 가능"
                        }
                    ]
                }
            }
        }
    }
    events = normalize_event_rows(
        sample_payload,
        default_date=date(2026, 6, 29),
        event_type="weather_alert",
        source="sample_event",
    )
    item = default_registry().get_item("cabbage")
    stress = [
        asdict(score_event_stress(event, item["event_profile"]["event_weights"]))
        for event in events
    ]
    print(json.dumps({"events": [asdict(event) for event in events], "stress": stress}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
