from pydantic import BaseModel
from typing import Optional


class TopFactor(BaseModel):
    factor: str
    contribution: float
    direction: str  # up / down


class ForecastResponse(BaseModel):
    item_code: str
    item_name: str
    base_date: str
    forecast: dict
    top_factors: list[TopFactor]
    national_supply_shock: Optional[float] = None
    confidence: str
    summary: str
    disclaimer: str = (
        "본 서비스의 예측 결과는 공공데이터와 자체 분석 모델을 기반으로 한 참고 정보입니다. "
        "실제 가격은 시장 상황에 따라 달라질 수 있으며, 의사결정의 최종 책임은 사용자에게 있습니다."
    )
