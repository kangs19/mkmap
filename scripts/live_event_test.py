from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import date
from collections.abc import Callable
from typing import Any

from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV
from mkmap_meta.connectors.normalizers import public_api_error


def encode(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return encode(asdict(value))
    if isinstance(value, list):
        return [encode(inner) for inner in value]
    if isinstance(value, dict):
        return {key: encode(inner) for key, inner in value.items()}
    return value


def run_live_event_test(
    *,
    connector_factory: Callable[[], Any],
    service_name: str,
    target_date: date,
    required_env: list[str],
    max_rows: int,
    strict: bool,
) -> int:
    missing_env = [env_name for env_name in required_env if not os.getenv(env_name)]
    if missing_env:
        print(
            json.dumps(
                {
                    "ok": False,
                    "service": service_name,
                    "reason": "Missing required environment variable(s)",
                    "missing_env": missing_env,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if strict else 0

    connector = connector_factory()
    payload = connector.fetch_payload(target_date)
    api_error = public_api_error(payload)
    events = [] if api_error else connector.normalize_payload(payload, target_date)
    print(
        json.dumps(
            {
                "ok": api_error is None,
                "service": service_name,
                "date": target_date.isoformat(),
                "api_error": api_error,
                "event_count": len(events),
                "events": encode(events[:max_rows]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def data_go_kr_required_env(*extra: str) -> list[str]:
    return [DATA_GO_KR_API_KEY_ENV, *extra]
