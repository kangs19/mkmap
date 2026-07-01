from sqlalchemy import String, Float, Date, DateTime, Integer, func, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.database import Base


class DailyPrice(Base):
    __tablename__ = "daily_prices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    market: Mapped[str] = mapped_column(String(100))
    grade: Mapped[str] = mapped_column(String(20))
    wholesale_price: Mapped[float] = mapped_column(Float, nullable=True)
    retail_price: Mapped[float] = mapped_column(Float, nullable=True)
    avg_year_price: Mapped[float] = mapped_column(Float, nullable=True)  # 평년가격
    prev_year_price: Mapped[float] = mapped_column(Float, nullable=True)  # 전년동기
    source: Mapped[str] = mapped_column(String(50), default="kamis")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_daily_prices_item_date", "item_code", "date"),
        UniqueConstraint("item_code", "date", "source", name="uq_daily_prices_item_date_source"),
    )
