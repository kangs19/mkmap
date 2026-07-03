"""회원 인증 — 가입/로그인/내정보. stdlib만 사용(pbkdf2 + HMAC 토큰)."""
import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
import re

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.community import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_TOKEN_TTL = 60 * 60 * 24 * 30  # 30일


def _secret() -> bytes:
    return get_settings().jwt_secret_key.encode()


# ── 비밀번호 (pbkdf2-sha256) ─────────────────────────────
def hash_password(raw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, 120_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(raw: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", raw.encode(), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ── 토큰 (HMAC-SHA256 서명) ─────────────────────────────
def make_token(user_id: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"uid": user_id, "exp": int(time.time()) + _TOKEN_TTL}).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def parse_token(token: str) -> int | None:
    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data.get("exp", 0) < time.time():
            return None
        return int(data["uid"])
    except Exception:
        return None


async def get_current_user(request: Request, db: AsyncSession) -> User | None:
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else None
    if not token:
        return None
    uid = parse_token(token)
    if uid is None:
        return None
    user = (await db.execute(select(User).where(User.id == uid, User.is_active == True))).scalar_one_or_none()  # noqa: E712
    return user


async def require_user(request: Request, db: AsyncSession) -> User:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "login_required", "message": "로그인이 필요합니다."})
    return user


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "nickname": u.nickname,
        "role": u.role,
        "role_label": {"general": "일반회원", "farmer": "인증 농부", "trader": "유통인", "admin": "관리자"}.get(u.role, u.role),
        "farmer_verified": u.farmer_verified,
        "region": u.region,
        "trust_score": u.trust_score,
    }


# ── 스키마 ───────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=6, max_length=100)
    nickname: str = Field(min_length=2, max_length=20)
    role: str = "general"          # general | farmer | trader (farmer/trader는 승인 전까지 미인증)
    region: str | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


# ── 엔드포인트 ───────────────────────────────────────────
@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    if body.role not in ("general", "farmer", "trader"):
        raise HTTPException(status_code=400, detail={"error": "invalid_role"})
    dup = (await db.execute(
        select(User).where((User.email == body.email.lower()) | (User.nickname == body.nickname))
    )).scalar_one_or_none()
    if dup:
        field = "이메일" if dup.email == body.email.lower() else "닉네임"
        raise HTTPException(status_code=409, detail={"error": "duplicate", "message": f"이미 사용 중인 {field}입니다."})

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        nickname=body.nickname,
        role=body.role,
        farmer_verified=False,
        region=body.region,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"token": make_token(user.id), "user": _user_out(user)}


@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials", "message": "이메일 또는 비밀번호가 올바르지 않습니다."})
    if not user.is_active:
        raise HTTPException(status_code=403, detail={"error": "inactive", "message": "사용 중지된 계정입니다."})
    user.last_login = sqlfunc.now()
    await db.commit()
    return {"token": make_token(user.id), "user": _user_out(user)}


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail={"error": "login_required"})
    return {"user": _user_out(user)}
