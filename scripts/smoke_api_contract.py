from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.api import parse_target_date
from mkmap_meta.services.api_services import ApiServiceStatusService
from mkmap_meta.services.signals import SignalService


def main() -> None:
    parsed = parse_target_date("2026-06-29")
    service = SignalService()
    api_service_status = ApiServiceStatusService().get_status()
    item_payload = service.get_item_signals("cabbage", parsed)
    today_payload = service.get_today_signals(parsed)
    contract = {
        "parsed_date": parsed.isoformat(),
        "item_keys": sorted(item_payload.keys()),
        "today_keys": sorted(today_payload.keys()),
        "api_service_keys": sorted(api_service_status.keys()),
        "cabbage_signal_count": len(item_payload["signals"]),
        "today_item_count": len(today_payload["items"]),
        "api_service_count": api_service_status["summary"]["total_services"],
    }
    print(json.dumps(contract, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
