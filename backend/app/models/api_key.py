from sqlalchemy import String, Boolean, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from datetime import datetime


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash:    Mapped[str]      = mapped_column(String(64), unique=True, index=True)
    name:        Mapped[str]      = mapped_column(String(100))          # 발급 대상 이름
    plan:        Mapped[str]      = mapped_column(String(20), default="free")  # free | pro | internal
    is_active:   Mapped[bool]     = mapped_column(Boolean, default=True)
    rate_limit:  Mapped[int]      = mapped_column(Integer, default=100)  # 요청/일
    created_at:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at:  Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_used:   Mapped[datetime] = mapped_column(DateTime, nullable=True)
    total_calls: Mapped[int]      = mapped_column(Integer, default=0)


class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"
    __table_args__ = {"extend_existing": True}

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash:   Mapped[str]      = mapped_column(String(64), index=True)
    endpoint:   Mapped[str]      = mapped_column(String(200))
    method:     Mapped[str]      = mapped_column(String(10))
    status:     Mapped[int]      = mapped_column(Integer)
    latency_ms: Mapped[int]      = mapped_column(Integer)
    called_at:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
