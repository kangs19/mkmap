from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.registry import default_registry


def main() -> None:
    registry = default_registry()
    plans = {
        item_code: asdict(plan)
        for item_code, plan in registry.build_all_engine_plans().items()
    }
    print(json.dumps(plans, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
