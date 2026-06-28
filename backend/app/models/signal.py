from sqlalchemy import String, Float, Date, DateTime, JSON, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.database import Base


class RegionSignal(Base):
    __tablename__ = "region_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    region_code: Mapped[str] = mapped_column(String(20), nullable=False)
    region_name: Mapped[str] = mapped_column(String(50))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=True)    # 0~100
    risk_level: Mapped[str] = mapped_column(String(20), nullable=True) # normal/caution/warning/high
    supply_shock: Mapped[float] = mapped_column(Float, nullable=True)  # -1.0 ~ +1.0
    price_effect: Mapped[str] = mapped_column(String(20), nullable=True)  # up/down/neutral
    weather_summary: Mapped[dict] = mapped_column(JSON, nullable=True)
    market_summary: Mapped[dict] = mapped_column(JSON, nullable=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_region_signals_item_region_date", "item_code", "region_code", "date"),
    )
