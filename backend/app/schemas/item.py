from pydantic import BaseModel
from typing import Optional


class ItemListResponse(BaseModel):
    item_code: str
    item_name: str
    category: str
    available: bool = True


class ItemRegionResponse(BaseModel):
    region_code: str
    region_name: str
    sub_regions: list[str]
    base_weight: float
    confidence: str
    display_level: Optional[str] = None   # main / sub
    risk_level: Optional[str] = None      # 동적 신호 이후 채워짐
    price_effect: Optional[str] = None
    summary: Optional[str] = None


class ItemRegionsResponse(BaseModel):
    item_code: str
    item_name: str
    base_date: str
    season: str
    mode: str  # static_metadata / dynamic_signal
    regions: list[ItemRegionResponse]


class ItemResponse(BaseModel):
    item_code: str
    item_name: str
    category: str
    storage_type: str
    price_volatility: str
    import_dependency: str
    weather_sensitivity: dict
    growth_calendar: dict
    demand_events: list
    substitute_items: list
    main_markets: list
    metadata_confidence: str
