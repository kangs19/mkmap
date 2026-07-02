from sqlalchemy import Column, Integer, String, Float, Date, UniqueConstraint
from app.database import Base


class RegionalMarketPrice(Base):
    """KAMIS 지역별 도매시장 가격 — market_code 별로 수집"""
    __tablename__ = "regional_market_price"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    item_code     = Column(String(50),  nullable=False, index=True)
    date          = Column(Date,        nullable=False, index=True)
    market_code   = Column(String(10),  nullable=False)  # "1101", "2100" ...
    market_name   = Column(String(50))                   # "서울가락", "부산엄궁" ...
    sido          = Column(String(20),  nullable=False)  # "서울", "부산" ...
    wholesale_price = Column(Float)
    retail_price    = Column(Float)

    __table_args__ = (
        UniqueConstraint("item_code", "date", "market_code", name="uq_regional_market_price"),
    )
