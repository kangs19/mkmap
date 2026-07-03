from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from app.database import Base


class DroughtIndex(Base):
    """전국 농업용수 저수율·강수 가뭄 지표 (MAFRA 669 집계).

    지역별 저수지코드(AREA_SPR_CD)는 시군구 매핑 테이블이 없어 우선 전국 지표로 저장.
    """
    __tablename__ = "drought_index"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    base_ym       = Column(String(6), nullable=False)   # 기준 연월 (예: 202607)
    date          = Column(Date, nullable=False)        # 수집 기준일
    reservoir_rate = Column(Float)                       # 전국 평균 저수율 (%)
    rainfall_avg   = Column(Float)                       # 전국 평균 강수량 (mm)
    region_count   = Column(Integer)                     # 집계 지역(저수지) 수

    __table_args__ = (
        UniqueConstraint("base_ym", name="uq_drought_index_ym"),
    )
