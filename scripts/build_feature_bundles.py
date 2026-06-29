from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.factory import build_default_pipeline


def encode(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, dict):
        return {key: encode(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [encode(inner) for inner in value]
    return value


def main() -> None:
    pipeline = build_default_pipeline()
    bundles = pipeline.build_all_bundles()
    print(json.dumps(encode(bundles), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
