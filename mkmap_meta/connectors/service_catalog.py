from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mkmap_meta.env import ensure_env_loaded


@dataclass(frozen=True)
class ApiService:
    provider: str
    code: str
    display_name: str
    engine_role: str
    required_env: list[str]
    status: str
    source_url: str | None = None
    base_url: str | None = None
    operation: str | None = None
    request_params: list[str] | None = None
    response_fields: list[str] | None = None
    notes: str | None = None

    @property
    def configured(self) -> bool:
        return all(bool(os.getenv(env_name)) for env_name in self.required_env)

    @property
    def missing_env(self) -> list[str]:
        return [env_name for env_name in self.required_env if not os.getenv(env_name)]


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "api_services.json"


def load_service_catalog(path: Path | str | None = None) -> list[ApiService]:
    catalog_path = Path(path) if path else default_catalog_path()
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    services: list[ApiService] = []

    for provider, provider_services in raw.items():
        for code, config in provider_services.items():
            services.append(
                ApiService(
                    provider=provider,
                    code=code,
                    display_name=config["display_name"],
                    engine_role=config["engine_role"],
                    required_env=list(config["required_env"]),
                    status=config["status"],
                    source_url=config.get("source_url"),
                    base_url=config.get("base_url"),
                    operation=config.get("operation"),
                    request_params=list(config.get("request_params", [])),
                    response_fields=list(config.get("response_fields", [])),
                    notes=config.get("notes"),
                )
            )

    return sorted(services, key=lambda service: (service.engine_role, service.provider, service.code))


def catalog_status(path: Path | str | None = None) -> list[dict[str, Any]]:
    ensure_env_loaded()
    return [
        {
            "provider": service.provider,
            "code": service.code,
            "display_name": service.display_name,
            "engine_role": service.engine_role,
            "status": service.status,
            "source_url": service.source_url,
            "base_url": service.base_url,
            "operation": service.operation,
            "request_params": service.request_params or [],
            "response_fields": service.response_fields or [],
            "notes": service.notes,
            "configured": service.configured,
            "missing_env": service.missing_env,
        }
        for service in load_service_catalog(path)
    ]
