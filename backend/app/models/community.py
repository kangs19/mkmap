from sqlalchemy import String, Boolean, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from datetime import datetime


class User(Base):
    """커뮤니티 회원 — 일반 / 인증농부 / 유통인 / 관리자"""
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    email:         Mapped[str]      = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str]      = mapped_column(String(200))
    nickname:      Mapped[str]      = mapped_column(String(50), unique=True, index=True)
    role:          Mapped[str]      = mapped_column(String(20), default="general")  # general | farmer | trader | admin
    farmer_verified: Mapped[bool]   = mapped_column(Boolean, default=False)  # 인증 농부 (관리자 승인)
    region:        Mapped[str]      = mapped_column(String(50), nullable=True)   # 활동 지역 (예: 괴산군)
    trust_score:   Mapped[int]      = mapped_column(Integer, default=0)
    is_active:     Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login:    Mapped[datetime] = mapped_column(DateTime, nullable=True)


class CommunityComment(Base):
    """지역 × 품목 커뮤니티 댓글 (예: 괴산군 배추)"""
    __tablename__ = "community_comments"
    __table_args__ = {"extend_existing": True}

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_code:  Mapped[str]      = mapped_column(String(30), index=True)
    region:     Mapped[str]      = mapped_column(String(50), index=True)  # 시군구 이름 (예: 괴산군, 해남군). "전국" 허용
    user_id:    Mapped[int]      = mapped_column(Integer, index=True)
    nickname:   Mapped[str]      = mapped_column(String(50))   # 표시용 스냅샷
    role:       Mapped[str]      = mapped_column(String(20), default="general")
    content:    Mapped[str]      = mapped_column(Text)
    parent_id:  Mapped[int]      = mapped_column(Integer, nullable=True, index=True)  # 대댓글
    likes:      Mapped[int]      = mapped_column(Integer, default=0)
    reports:    Mapped[int]      = mapped_column(Integer, default=0)   # 신고 수
    is_deleted: Mapped[bool]     = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FieldReport(Base):
    """우리지역 평가하기 — 인증 농부 현장 제보. AI 학습에 사용하지 않음(현장 신호 전용)."""
    __tablename__ = "field_reports"
    __table_args__ = {"extend_existing": True}

    id:            Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_code:     Mapped[str]      = mapped_column(String(30), index=True)
    region:        Mapped[str]      = mapped_column(String(50), index=True)
    user_id:       Mapped[int]      = mapped_column(Integer, index=True)
    nickname:      Mapped[str]      = mapped_column(String(50))
    growth:        Mapped[str]      = mapped_column(String(10))               # good | normal | bad
    pest:          Mapped[str]      = mapped_column(String(10))               # none | some | severe
    shipment:      Mapped[str]      = mapped_column(String(10))               # up | normal | down
    weather_damage: Mapped[str]     = mapped_column(String(100), nullable=True)  # 폭염,가뭄,태풍,우박,호우 (콤마 구분)
    price_feeling: Mapped[str]      = mapped_column(String(10))               # up | same | down
    comment:       Mapped[str]      = mapped_column(String(300), nullable=True)  # 한줄평
    created_at:    Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
