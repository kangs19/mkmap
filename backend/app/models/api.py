from sqlalchemy import String, Integer, DateTime, Boolean, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free/starter/business/enterprise
    daily_limit: Mapped[int] = mapped_column(Integer, default=100)
    monthly_limit: Mapped[int] = mapped_column(Integer, default=3000)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(Integer, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10))
    status_code: Mapped[int] = mapped_column(Integer)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=True)
    client_ip: Mapped[str] = mapped_column(String(50), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_api_usage_key_date", "api_key_id", "requested_at"),
    )
