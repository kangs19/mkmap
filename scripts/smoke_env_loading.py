from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import load_env_file


TMP_ENV = REPO_ROOT / "_tmp_smoke.env"


def main() -> int:
    try:
        os.environ.pop("MKMAP_SMOKE_ENV", None)
        TMP_ENV.write_text("MKMAP_SMOKE_ENV=loaded\n", encoding="utf-8")
        loaded = load_env_file(TMP_ENV)
        if os.getenv("MKMAP_SMOKE_ENV") != "loaded":
            raise RuntimeError("env value was not loaded")
        if loaded.get("MKMAP_SMOKE_ENV") != "loaded":
            raise RuntimeError("loaded map did not include env value")
        print("env-loading-ok")
        return 0
    finally:
        os.environ.pop("MKMAP_SMOKE_ENV", None)
        if TMP_ENV.exists():
            TMP_ENV.unlink()


if __name__ == "__main__":
    sys.exit(main())

