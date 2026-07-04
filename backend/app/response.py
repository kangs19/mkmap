"""표준 API 응답 envelope (Bible Vol.3).

    { "success": bool, "data": ..., "meta": {...}, "error": {...}|null }

기존 엔드포인트(원시 JSON)는 프론트 호환을 위해 유지하고,
신규/이관 엔드포인트부터 이 helper를 사용한다. (점진적 정렬)
"""
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok(data: Any = None, meta: dict | None = None) -> dict:
    return {
        "success": True,
        "data": data,
        "meta": {"timestamp": _now_iso(), **(meta or {})},
        "error": None,
    }


def err(code: str, message: str = "", status: int | None = None, meta: dict | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "meta": {"timestamp": _now_iso(), **(meta or {})},
        "error": {"code": code, "message": message, **({"status": status} if status else {})},
    }


def paginated(items: list, page: int, per_page: int, total: int, meta: dict | None = None) -> dict:
    return ok(items, meta={
        "pagination": {"page": page, "per_page": per_page, "total": total,
                       "pages": (total + per_page - 1) // per_page if per_page else 0},
        **(meta or {}),
    })
