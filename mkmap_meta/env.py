from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env_file(path: Path | str | None = None, *, override: bool = False) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from .env without requiring python-dotenv.

    This intentionally supports only the common .env shape used by this project.
    Values already present in the process environment are preserved unless
    override=True.
    """

    env_path = Path(path) if path else repo_root() / ".env"
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded[key] = value

    return loaded


def ensure_env_loaded() -> None:
    load_env_file()

