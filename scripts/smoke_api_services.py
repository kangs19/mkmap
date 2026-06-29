from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.services.api_services import ApiServiceStatusService


def main() -> int:
    payload = ApiServiceStatusService().get_status()
    if payload["summary"]["total_services"] == 0:
        raise RuntimeError("API service catalog is empty")
    if "price_market" not in payload["summary"]["by_engine_role"]:
        raise RuntimeError("price_market services are missing from catalog")
    if "agri_weather" not in payload["summary"]["by_engine_role"]:
        raise RuntimeError("agri_weather services are missing from catalog")

    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
