from sqlalchemy import String, Float, JSON, Text, DateTime, ForeignKey, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from app.database import Base


class Item(Base):
    __tablename__ = "items"

    item_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    wholesale_unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    retail_unit: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    storage_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    price_volatility: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    import_dependency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    weather_sensitivity: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    growth_calendar: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    demand_events: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    substitute_items: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    main_markets: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metadata_confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="draft")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    regions: Mapped[list["ItemRegion"]] = relationship("ItemRegion", back_populates="item")


class ItemRegion(Base):
    __tablename__ = "item_regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), ForeignKey("items.item_code"))
    region_code: Mapped[str] = mapped_column(String(20))
    region_name: Mapped[str] = mapped_column(String(50))
    is_primary: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    sub_region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 확장 필드 (선택)
    season: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    season_description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sub_regions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    base_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    center_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    center_lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item: Mapped["Item"] = relationship("Item", back_populates="regions")


class ItemEvent(Base):
    __tablename__ = "item_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), ForeignKey("items.item_code"))
    event_name: Mapped[str] = mapped_column(String(100))
    event_months: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    effect: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    importance: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
