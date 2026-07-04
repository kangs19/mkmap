"""RBAC — 역할·권한 매트릭스 (PRD Ch.10/13, Bible Vol.3).

기존 인증(get_current_user, Bearer 토큰)을 감싸 표준 권한 계층을 제공한다.
신규/이관 엔드포인트는 여기의 의존성을 사용한다. (점진적 정렬)
"""
from enum import Enum
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db


class Role(str, Enum):
    GUEST = "guest"          # 비로그인 (조회만)
    GENERAL = "general"      # 일반회원
    FARMER = "farmer"        # 농부 (farmer_verified로 인증 여부 구분)
    TRADER = "trader"        # 유통인
    RESEARCH = "research"    # 연구/기관 (향후)
    BUSINESS = "business"    # 기업 (향후)
    ADMIN = "admin"


# 권한 매트릭스 — 기능별 허용 역할 (PRD 기반). 문서화 + 코드 단일 출처.
PERMISSIONS: dict[str, set[str]] = {
    "read_public":       {"*"},                                   # 지도·가격·예측 조회
    "comment_write":     {"general", "farmer", "trader", "admin"},
    "field_report_write": {"farmer", "trader", "admin"},          # + farmer_verified 필요
    "admin_ops":         {"admin"},
}


def can(role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(permission, set())
    return "*" in allowed or role in allowed


async def current_user_optional(request: Request, db: AsyncSession = Depends(get_db)):
    """로그인 사용자 or None (게스트 허용)."""
    from app.routers.auth_user import get_current_user
    return await get_current_user(request, db)


def require_role(*roles: str):
    """지정 역할만 허용하는 FastAPI 의존성."""
    async def _dep(request: Request, db: AsyncSession = Depends(get_db)):
        from app.routers.auth_user import get_current_user
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail={"error": "login_required"})
        if roles and user.role not in roles and user.role != "admin":
            raise HTTPException(status_code=403, detail={"error": "forbidden", "need": list(roles)})
        return user
    return _dep


def require_verified_producer():
    """인증된 농부/유통인만 (현장 제보 등)."""
    async def _dep(request: Request, db: AsyncSession = Depends(get_db)):
        from app.routers.auth_user import get_current_user
        user = await get_current_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail={"error": "login_required"})
        ok = user.role == "admin" or (user.role in ("farmer", "trader") and user.farmer_verified)
        if not ok:
            raise HTTPException(status_code=403, detail={
                "error": "verified_producer_only",
                "message": "휴대폰 인증을 마친 농부·유통인만 가능합니다.",
            })
        return user
    return _dep
