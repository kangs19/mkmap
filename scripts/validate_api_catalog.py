from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.service_catalog import load_service_catalog


ENV_EXAMPLE = REPO_ROOT / ".env.example"


def read_env_example_names() -> set[str]:
    names: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        names.add(stripped.split("=", 1)[0])
    return names


def main() -> int:
    env_names = read_env_example_names()
    errors: list[str] = []

    seen_codes: set[tuple[str, str]] = set()
    for service in load_service_catalog():
        key = (service.provider, service.code)
        if key in seen_codes:
            errors.append(f"duplicate service code: {service.provider}.{service.code}")
        seen_codes.add(key)

        missing_env_examples = sorted(set(service.required_env) - env_names)
        if missing_env_examples:
            errors.append(
                f"{service.provider}.{service.code}: required_env missing from .env.example: "
                + ", ".join(missing_env_examples)
            )

    if errors:
        print("API catalog validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"API catalog validation passed: {len(seen_codes)} service(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
