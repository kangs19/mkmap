from sqlalchemy import String, Float, Integer, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.database import Base


class CropProduction(Base):
    """KOSIS 연간 재배면적 + 생산량 (통계청 농작물생산조사)"""
    __tablename__ = "crop_productions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    area_ha: Mapped[float] = mapped_column(Float, nullable=True)        # 재배면적 (ha)
    production_ton: Mapped[float] = mapped_column(Float, nullable=True) # 생산량 (톤)
    yield_per_ha: Mapped[float] = mapped_column(Float, nullable=True)   # 10a당 수량 (kg)
    source: Mapped[str] = mapped_column(String(50), default="kosis")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_crop_productions_item_year", "item_code", "year", unique=True),
    )
