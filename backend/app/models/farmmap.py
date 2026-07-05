from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FarmMapCropRegion(Base):
    """Aggregated FarmMap spatial crop context for map and model features.

    Raw parcel geometries can be too heavy for the public map. Store normalized
    crop/region summaries here, then serve simplified map layers from this table.
    """

    __tablename__ = "farmmap_crop_regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    source_crop_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sido: Mapped[str] = mapped_column(String(30), nullable=False)
    sigungu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    farm_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry_level: Mapped[str] = mapped_column(String(20), default="sigungu")
    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="farmmap")
    confidence: Mapped[str] = mapped_column(String(20), default="source_checked")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "item_code",
            "sido",
            "sigungu",
            "source_file",
            name="uq_farmmap_crop_region_source",
        ),
        Index("ix_farmmap_crop_regions_item_region", "item_code", "sido", "sigungu"),
    )


class FarmMapLanduseRegion(Base):
    """Aggregated FarmMap land-use context by region.

    Province FarmMap sources checked so far expose land-use classes rather than
    crop names. Keep this table separate from crop-specific acreage so the UI
    and model cannot accidentally present land-use area as crop area.
    """

    __tablename__ = "farmmap_landuse_regions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sido: Mapped[str] = mapped_column(String(30), nullable=False)
    sigungu: Mapped[str | None] = mapped_column(String(60), nullable=True)
    landuse_class: Mapped[str] = mapped_column(String(30), nullable=False)
    parcel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="farmmap")
    confidence: Mapped[str] = mapped_column(String(30), default="landuse_only")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "sido",
            "sigungu",
            "landuse_class",
            "source_file",
            name="uq_farmmap_landuse_region_source",
        ),
        Index("ix_farmmap_landuse_regions_region", "sido", "sigungu", "landuse_class"),
    )


class FarmMapSourceFile(Base):
    """Audit record for a FarmMap source file before import."""

    __tablename__ = "farmmap_source_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(100), default="EPIS/FarmMap")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    province: Mapped[str | None] = mapped_column(String(30), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    detected_fields_json: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    detected_crops_json: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    import_status: Mapped[str] = mapped_column(String(30), default="audited")
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
