from sqlalchemy import String, Float, Date, DateTime, Boolean, func, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date, datetime
from app.database import Base


class DailyWeather(Base):
    __tablename__ = "daily_weather"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    region_code: Mapped[str] = mapped_column(String(20), nullable=False)
    region_name: Mapped[str] = mapped_column(String(50))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    avg_temp: Mapped[float] = mapped_column(Float, nullable=True)
    max_temp: Mapped[float] = mapped_column(Float, nullable=True)
    min_temp: Mapped[float] = mapped_column(Float, nullable=True)
    precipitation: Mapped[float] = mapped_column(Float, nullable=True)
    humidity: Mapped[float] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float] = mapped_column(Float, nullable=True)
    sunshine_hours: Mapped[float] = mapped_column(Float, nullable=True)
    snowfall: Mapped[float] = mapped_column(Float, nullable=True)
    heat_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    cold_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    heavy_rain_alert: Mapped[bool] = mapped_column(Boolean, default=False)
    normal_avg_temp: Mapped[float] = mapped_column(Float, nullable=True)   # 평년 평균기온
    normal_precip: Mapped[float] = mapped_column(Float, nullable=True)     # 평년 강수량
    source: Mapped[str] = mapped_column(String(50), default="kma_asos")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_daily_weather_region_date", "region_code", "date"),
        UniqueConstraint("region_code", "date", "source", name="uq_daily_weather_region_date_source"),
    )
