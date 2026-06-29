from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from mkmap_meta.connectors.service_catalog import catalog_status


class ApiServiceStatusService:
    """API-facing service for external data-source configuration status."""

    def get_status(self) -> dict[str, Any]:
        services = catalog_status()
        configured_count = sum(1 for service in services if service["configured"])
        missing_required = [
            service
            for service in services
            if not service["configured"] and service["status"] != "optional_after_core"
        ]

        by_role: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "configured": 0})
        for service in services:
            role = service["engine_role"]
            by_role[role]["total"] += 1
            if service["configured"]:
                by_role[role]["configured"] += 1

        return {
            "summary": {
                "total_services": len(services),
                "configured_services": configured_count,
                "missing_required_services": len(missing_required),
                "by_provider": dict(Counter(service["provider"] for service in services)),
                "by_engine_role": dict(sorted(by_role.items())),
            },
            "services": services,
        }

