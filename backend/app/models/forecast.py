from sqlalchemy import String, Float, Date, DateTime, JSON, func, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.database import Base


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    base_date: Mapped[date] = mapped_column(Date, nullable=False)
    model_version: Mapped[str] = mapped_column(String(50))
    direction_14d: Mapped[str] = mapped_column(String(20), nullable=True)  # up/down/neutral
    up_probability_14d: Mapped[float] = mapped_column(Float, nullable=True)
    surge_probability_14d: Mapped[float] = mapped_column(Float, nullable=True)
    volatility_risk_30d: Mapped[str] = mapped_column(String(20), nullable=True)
    bottom_probability: Mapped[float] = mapped_column(Float, nullable=True)
    top_factors: Mapped[list] = mapped_column(JSON, nullable=True)
    national_supply_shock: Mapped[float] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("item_code", "base_date", name="uq_forecasts_item_date"),
        Index("ix_forecasts_item_date", "item_code", "base_date"),
    )
