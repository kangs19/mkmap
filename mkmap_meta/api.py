from __future__ import annotations

from datetime import date
from typing import Any

from mkmap_meta.services.api_services import ApiServiceStatusService
from mkmap_meta.services.signals import SignalService


def parse_target_date(target_date: str | None) -> date | None:
    return date.fromisoformat(target_date) if target_date else None


def create_signal_router() -> Any:
    """Create a FastAPI router for MK-MAP signal endpoints.

    FastAPI is imported lazily so metadata tooling can run in environments where
    the API server dependencies are not installed yet.
    """

    try:
        from fastapi import APIRouter, Query
    except ImportError as exc:
        raise RuntimeError("FastAPI is required to create the signal router") from exc

    router = APIRouter()
    signal_service = SignalService()
    api_service_status = ApiServiceStatusService()

    @router.get("/api/v1/items/{item_code}/signals")
    def get_item_signals(item_code: str, target_date: str | None = Query(default=None)) -> dict[str, Any]:
        return signal_service.get_item_signals(item_code, parse_target_date(target_date))

    @router.get("/api/v1/signals/today")
    def get_today_signals(target_date: str | None = Query(default=None)) -> dict[str, Any]:
        return signal_service.get_today_signals(parse_target_date(target_date))

    @router.get("/api/v1/items/{item_code}/meta-engine")
    def get_item_meta_engine(item_code: str) -> dict[str, Any]:
        registry = signal_service.registry
        item = registry.get_item(item_code)
        plan = registry.build_engine_plan(item_code)
        return {
            "item": item,
            "engine_plan": {
                "item_code": plan.item_code,
                "item_name": plan.item_name,
                "engines": plan.engines,
                "source_coverage": plan.source_coverage,
                "risk_weights": plan.risk_weights,
                "critical_weather_factors": plan.critical_weather_factors,
                "manual_review_required": plan.manual_review_required,
            },
        }

    @router.get("/api/v1/api-services")
    def get_api_services() -> dict[str, Any]:
        return api_service_status.get_status()

    return router


def create_app() -> Any:
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("FastAPI is required to create the app") from exc

    app = FastAPI(
        title="MK-MAP Meta Engine API",
        description="Metadata-driven agricultural price risk signal engine",
        version="0.1.0",
    )
    app.include_router(create_signal_router())
    return app


app = None
