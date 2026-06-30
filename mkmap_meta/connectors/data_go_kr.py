from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from mkmap_meta.connectors.http import SimpleHttpClient


DATA_GO_KR_API_KEY_ENV = "DATA_GO_KR_API_KEY"


@dataclass(frozen=True)
class DataGoKrService:
    name: str
    base_url: str
    default_params: dict[str, Any]
    api_key_param: str = "serviceKey"


class DataGoKrClient:
    """Shared client for data.go.kr services."""

    def __init__(self, api_key: str | None = None, http: SimpleHttpClient | None = None) -> None:
        self.api_key = api_key or os.getenv(DATA_GO_KR_API_KEY_ENV)
        if not self.api_key:
            raise ValueError(f"Missing {DATA_GO_KR_API_KEY_ENV}")
        self.http = http or SimpleHttpClient()

    def get(self, service: DataGoKrService, operation_path: str = "", **params: Any) -> Any:
        url = service.base_url.rstrip("/")
        if operation_path:
            url = f"{url}/{operation_path.lstrip('/')}"

        request_params = {
            service.api_key_param: self.api_key,
            **service.default_params,
            **params,
        }
        response = self.http.get(url, request_params)
        content_type = response.headers.get("Content-Type", "")
        if "json" in content_type.lower() or response.text.lstrip().startswith("{"):
            return response.json()
        return response.text


DATA_GO_KR_SERVICES = {
    "at_market_settlement": DataGoKrService(
        name="한국농수산식품유통공사 전국 공영도매시장 정산정보",
        base_url="",
        default_params={"type": "json"},
    ),
    "at_regional_price": DataGoKrService(
        name="한국농수산식품유통공사 지역별 품목별 도소매 가격정보",
        base_url="",
        default_params={"type": "json"},
    ),
    "rda_agri_weather": DataGoKrService(
        name="농촌진흥청 국립농업과학원 농업기상 상세 관측데이터",
        base_url="",
        default_params={"type": "json"},
    ),
    "kma_impact_forecast": DataGoKrService(
        name="기상청 영향예보 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_weather_chart": DataGoKrService(
        name="기상청 일기도 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_satellite": DataGoKrService(
        name="기상청 위성영상 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_typhoon": DataGoKrService(
        name="기상청 태풍정보 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_midterm_forecast": DataGoKrService(
        name="기상청 중기예보 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_weather_alert": DataGoKrService(
        name="기상청 기상특보 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
    "kma_crop_weather": DataGoKrService(
        name="기상청 작물별 농업주산지 상세날씨 조회서비스",
        base_url="",
        default_params={"dataType": "JSON"},
    ),
}
