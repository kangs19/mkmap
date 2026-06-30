"""
API 키 인증 + Rate Limiting + 사용량 로깅
"""
import hashlib, secrets, time
from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from fastapi import Request, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.api_key import ApiKey, ApiUsageLog

# ── 인메모리 rate limiter (일별 카운터) ─────────────────────
_rate_counter: dict[str, dict[str, int]] = defaultdict(dict)  # key_hash → {date: count}

# 인증 불필요 경로 (지도·대시보드 UI + 위젯)
PUBLIC_PATHS = {
    "/", "/dashboard", "/forecast-explanation", "/widget", "/widget/embed",
    "/admin/ui",  # 관리자 HTML UI (API 호출은 X-Admin-Key로 별도 보호)
    "/docs", "/openapi.json", "/redoc", "/health",
    "/map_standalone.html", "/index.html",
}
# /admin/ 은 X-Admin-Key로 자체 보호 — API키 미들웨어는 통과시킴
PUBLIC_PREFIXES = ("/maps/", "/static/", "/admin/")

# REQUIRE_API_KEY=true 환경변수로 API 키 인증 활성화
# false(기본)이면 /api/ 경로는 공개 — 위젯·WordPress 임베드 호환
import os as _os
_API_AUTH_ENABLED = _os.environ.get("REQUIRE_API_KEY", "false").lower() == "true"

if not _API_AUTH_ENABLED:
    # 키 배포 전까지 /api/ 전체 공개 (rate limit 로깅만 동작)
    PUBLIC_PREFIXES = ("/maps/", "/static/", "/admin/", "/api/")


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_key() -> str:
    return "agri_" + secrets.token_urlsafe(32)


async def verify_api_key(request: Request) -> Optional[str]:
    """
    X-API-Key 헤더 또는 ?api_key= 쿼리로 인증.
    공개 경로는 None 반환(통과). 보호 경로는 키 없으면 401.
    """
    path = request.url.path
    if path.startswith("/api/v1/items/") and path.endswith("/forecast/explanation"):
        return None

    # 공개 경로 통과
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return None

    raw = (
        request.headers.get("X-API-Key")
        or request.query_params.get("api_key")
    )
    if not raw:
        raise HTTPException(status_code=401, detail={
            "error": "missing_api_key",
            "message": "X-API-Key 헤더 또는 ?api_key= 파라미터가 필요합니다.",
        })

    key_hash = hash_key(raw)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active == True,
            )
        )
        api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail={
            "error": "invalid_api_key",
            "message": "유효하지 않은 API 키입니다.",
        })

    # 만료 확인
    if api_key.expires_at and api_key.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail={
            "error": "expired_api_key",
            "message": "만료된 API 키입니다.",
        })

    # Rate limit 확인
    today = str(date.today())
    _rate_counter[key_hash].setdefault(today, 0)
    _rate_counter[key_hash][today] += 1

    if _rate_counter[key_hash][today] > api_key.rate_limit:
        raise HTTPException(status_code=429, detail={
            "error": "rate_limit_exceeded",
            "message": f"일일 요청 한도({api_key.rate_limit}회)를 초과했습니다.",
            "limit": api_key.rate_limit,
            "used": _rate_counter[key_hash][today],
        })

    return key_hash


async def log_request(key_hash: Optional[str], endpoint: str, method: str,
                       status: int, latency_ms: int):
    """비동기 사용량 로그 기록"""
    if not key_hash:
        return
    async with AsyncSessionLocal() as db:
        db.add(ApiUsageLog(
            key_hash=key_hash,
            endpoint=endpoint,
            method=method,
            status=status,
            latency_ms=latency_ms,
        ))
        await db.execute(
            update(ApiKey)
            .where(ApiKey.key_hash == key_hash)
            .values(
                total_calls=ApiKey.total_calls + 1,
                last_used=func.now(),
            )
        )
        await db.commit()
