from sqlalchemy import String, Float, JSON, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.database import Base


class Item(Base):
    __tablename__ = "items"

    item_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50))
    wholesale_unit: Mapped[str] = mapped_column(String(30))
    retail_unit: Mapped[str] = mapped_column(String(30))
    storage_type: Mapped[str] = mapped_column(String(20))  # short / medium / long
    price_volatility: Mapped[str] = mapped_column(String(20))  # high / medium / low
    import_dependency: Mapped[str] = mapped_column(String(20))
    weather_sensitivity: Mapped[dict] = mapped_column(JSON)
    growth_calendar: Mapped[dict] = mapped_column(JSON)
    demand_events: Mapped[list] = mapped_column(JSON)
    substitute_items: Mapped[list] = mapped_column(JSON)
    main_markets: Mapped[list] = mapped_column(JSON)
    metadata_confidence: Mapped[str] = mapped_column(String(20), default="draft")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    regions: Mapped[list["ItemRegion"]] = relationship("ItemRegion", back_populates="item")


class ItemRegion(Base):
    __tablename__ = "item_regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), ForeignKey("items.item_code"))
    season: Mapped[str] = mapped_column(String(20))  # spring / summer / autumn / winter
    season_description: Mapped[str] = mapped_column(String(200))
    region_code: Mapped[str] = mapped_column(String(20))
    region_name: Mapped[str] = mapped_column(String(50))
    sub_regions: Mapped[list] = mapped_column(JSON)
    base_weight: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(20))  # high / medium / low / draft
    source_type: Mapped[str] = mapped_column(String(50))
    source_name: Mapped[str] = mapped_column(String(200))
    source_note: Mapped[str] = mapped_column(Text, nullable=True)
    center_lat: Mapped[float] = mapped_column(Float, nullable=True)
    center_lng: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item: Mapped["Item"] = relationship("Item", back_populates="regions")


class ItemEvent(Base):
    __tablename__ = "item_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), ForeignKey("items.item_code"))
    event_name: Mapped[str] = mapped_column(String(100))
    event_months: Mapped[list] = mapped_column(JSON, nullable=True)
    effect: Mapped[str] = mapped_column(String(50))  # demand_up / demand_down / supply_up
    importance: Mapped[str] = mapped_column(String(20))  # high / medium / low
