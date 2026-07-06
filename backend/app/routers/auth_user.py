"""회원 인증 — 가입/로그인/내정보 + 휴대폰 SMS 인증. stdlib만 사용(pbkdf2 + HMAC 토큰)."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.community import User, PhoneVerification
from app.sms import send_sms, sms_configured

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_TOKEN_TTL = 60 * 60 * 24 * 30  # 30일
_OTP_TTL = 60 * 5               # 인증번호 유효 5분
_OTP_MAX_ATTEMPTS = 5           # 코드 검증 최대 시도
_PHONE_TOKEN_TTL = 60 * 20      # 인증완료 토큰 20분 (가입 완료까지)


def _secret() -> bytes:
    return get_settings().jwt_secret_key.encode()


def _norm_phone(raw: str) -> str:
    return re.sub(r"[^0-9]", "", raw or "")


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


# 휴대폰 인증완료 토큰 (가입 시 폰 소유 증명)
def make_phone_token(phone: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"ph": phone, "exp": int(time.time()) + _PHONE_TOKEN_TTL}).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_secret(), ("PH:" + payload).encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def parse_phone_token(token: str) -> str | None:
    try:
        payload, sig = token.rsplit(".", 1)
        expected = hmac.new(_secret(), ("PH:" + payload).encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data.get("exp", 0) < time.time():
            return None
        return str(data["ph"])
    except Exception:
        return None


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
        "role_label": {
            "general": "일반회원",
            "farmer": "인증 농부" if u.farmer_verified else "농부 (인증 대기)",
            "trader": "인증 유통인" if u.farmer_verified else "유통인 (인증 대기)",
            "admin": "관리자",
        }.get(u.role, u.role),
        "farmer_verified": u.farmer_verified,
        "phone_verified": getattr(u, "phone_verified", False),
        "region": u.region,
        "trust_score": u.trust_score,
    }


# ── 스키마 ───────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(min_length=6, max_length=100)
    nickname: str = Field(min_length=2, max_length=20)
    role: str = "general"          # general | farmer | trader
    region: str | None = None
    phone: str | None = None       # 휴대폰 인증 시
    phone_token: str | None = None # 휴대폰 인증완료 토큰

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("올바른 이메일 형식이 아닙니다.")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class PhoneSendIn(BaseModel):
    phone: str


class PhoneVerifyIn(BaseModel):
    phone: str
    code: str


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

    # 휴대폰 인증 처리 — farmer/trader는 인증 필수
    phone = None
    phone_verified = False
    if body.phone_token:
        tok_phone = parse_phone_token(body.phone_token)
        if not tok_phone or tok_phone != _norm_phone(body.phone or ""):
            raise HTTPException(status_code=400, detail={"error": "invalid_phone_token", "message": "휴대폰 인증이 만료되었거나 일치하지 않습니다. 다시 인증해 주세요."})
        phone = tok_phone
        phone_verified = True
        # 같은 번호로 이미 가입된 계정 방지
        used = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
        if used:
            raise HTTPException(status_code=409, detail={"error": "phone_in_use", "message": "이미 가입에 사용된 휴대폰 번호입니다."})

    if body.role in ("farmer", "trader") and not phone_verified:
        raise HTTPException(status_code=400, detail={
            "error": "phone_required",
            "message": "농부·유통인 회원은 휴대폰 인증이 필요합니다.",
        })

    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        nickname=body.nickname,
        role=body.role,
        # 휴대폰 인증을 자격 인증으로 인정 (사용자 선택 방식)
        farmer_verified=(body.role in ("farmer", "trader") and phone_verified),
        phone=phone,
        phone_verified=phone_verified,
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
        raise HTTPException(status_code=401, detail={"error": "login_required", "message": "로그인이 필요합니다."})
    return {"user": _user_out(user)}


# ── 휴대폰 SMS 인증 ──────────────────────────────────────
@router.post("/phone/send")
async def phone_send(body: PhoneSendIn, db: AsyncSession = Depends(get_db)):
    phone = _norm_phone(body.phone)
    if len(phone) < 9 or len(phone) > 20:
        raise HTTPException(status_code=400, detail={"error": "invalid_phone", "message": "올바른 휴대폰 번호를 입력해 주세요."})

    now = datetime.utcnow()
    # 재발송 제한: 30초 이내 발송 금지
    recent = (await db.execute(
        select(PhoneVerification)
        .where(PhoneVerification.phone == phone)
        .order_by(PhoneVerification.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if recent and recent.created_at and (now - recent.created_at).total_seconds() < 30:
        raise HTTPException(status_code=429, detail={"error": "too_soon", "message": "인증번호는 30초 후에 다시 요청할 수 있습니다."})

    code = f"{secrets.randbelow(1000000):06d}"
    pv = PhoneVerification(
        phone=phone,
        code_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=now + timedelta(seconds=_OTP_TTL),
    )
    db.add(pv)
    await db.commit()

    sent = await send_sms(phone, f"[MK-MAP] 인증번호 {code} (5분 내 입력)")
    resp = {"ok": True, "expires_in": _OTP_TTL}
    if not sent:
        # 미설정 시 개발환경에서만 코드 반환 (운영에서는 절대 노출 안 함)
        if get_settings().app_env != "production":
            resp["dev_code"] = code
            resp["dev_note"] = "SMS 미설정 — 개발환경 응답에만 코드 노출"
        else:
            raise HTTPException(status_code=503, detail={
                "error": "sms_unavailable",
                "message": "문자 발송이 아직 설정되지 않았습니다. 관리자에게 문의해 주세요.",
            })
    return resp


@router.post("/phone/verify")
async def phone_verify(body: PhoneVerifyIn, db: AsyncSession = Depends(get_db)):
    phone = _norm_phone(body.phone)
    code = body.code.strip()
    if len(phone) < 9 or len(phone) > 20:
        raise HTTPException(status_code=400, detail={"error": "invalid_phone", "message": "올바른 휴대폰 번호를 입력해 주세요."})
    if len(code) < 4 or len(code) > 6 or not code.isdigit():
        raise HTTPException(status_code=400, detail={"error": "invalid_code", "message": "인증번호를 다시 확인해 주세요."})
    now = datetime.utcnow()
    pv = (await db.execute(
        select(PhoneVerification)
        .where(PhoneVerification.phone == phone, PhoneVerification.verified == False)  # noqa: E712
        .order_by(PhoneVerification.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not pv:
        raise HTTPException(status_code=400, detail={"error": "no_request", "message": "먼저 인증번호를 요청해 주세요."})
    if pv.expires_at and now > pv.expires_at:
        raise HTTPException(status_code=400, detail={"error": "expired", "message": "인증번호가 만료되었습니다. 다시 요청해 주세요."})
    if pv.attempts >= _OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail={"error": "too_many", "message": "시도 횟수를 초과했습니다. 다시 요청해 주세요."})

    pv.attempts += 1
    if hashlib.sha256(code.encode()).hexdigest() != pv.code_hash:
        await db.commit()
        raise HTTPException(status_code=400, detail={"error": "wrong_code", "message": "인증번호가 일치하지 않습니다."})

    pv.verified = True
    await db.commit()
    return {"ok": True, "phone_token": make_phone_token(phone), "phone": phone}
