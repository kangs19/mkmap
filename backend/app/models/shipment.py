from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from app.database import Base


class ShipmentShare(Base):
    """실시간 경매 산지(plor_nm) 거래량 기반 지역별 출하 비중.

    하드코딩 데모 생산비중을 대체 — 실제 출하량 점유율(계절 반영).
    """
    __tablename__ = "shipment_share"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    item_code  = Column(String(30), nullable=False, index=True)
    sido       = Column(String(20), nullable=False)     # 표준 시도명 (강원/전남 ...)
    base_date  = Column(Date, nullable=False)
    share_pct  = Column(Float)                            # 전국 대비 출하 비중 (%)
    volume     = Column(Float)                            # 집계 거래량 (kg 등)

    __table_args__ = (
        UniqueConstraint("item_code", "sido", "base_date", name="uq_shipment_share"),
    )
