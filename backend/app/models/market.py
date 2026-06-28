from sqlalchemy import String, Float, Date, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.database import Base


class DailyMarket(Base):
    __tablename__ = "daily_market"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    market: Mapped[str] = mapped_column(String(100))
    origin_region: Mapped[str] = mapped_column(String(100), nullable=True)  # 산지
    volume_kg: Mapped[float] = mapped_column(Float, nullable=True)     # 반입량(kg)
    trade_volume: Mapped[float] = mapped_column(Float, nullable=True)  # 거래량
    trade_amount: Mapped[float] = mapped_column(Float, nullable=True)  # 거래금액
    source: Mapped[str] = mapped_column(String(50), default="kamis")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_daily_market_item_date", "item_code", "date"),
    )
