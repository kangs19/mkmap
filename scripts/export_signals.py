from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.services.signals import SignalService


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MK-MAP risk signals as JSON.")
    parser.add_argument("--item", help="Item code. Omit to export today summary for all items.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format.")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else None
    service = SignalService()
    payload = service.get_item_signals(args.item, target_date) if args.item else service.get_today_signals(target_date)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
