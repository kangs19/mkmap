from pydantic import BaseModel
from typing import Optional


class RegionSignalResponse(BaseModel):
    item_code: str
    region_code: str
    region_name: str
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    supply_shock: Optional[float] = None
    price_effect: Optional[str] = None
    weather_summary: Optional[dict] = None
    market_summary: Optional[dict] = None
    summary: Optional[str] = None
