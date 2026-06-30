from __future__ import annotations

import os
from datetime import date
from typing import Any
from xml.etree import ElementTree as ET

from mkmap_meta.connectors.base import WeatherConnector
from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV, DataGoKrClient, DataGoKrService
from mkmap_meta.connectors.normalizers import extract_rows, first_present, parse_date, parse_float, public_api_error
from mkmap_meta.models import WeatherFeature
from mkmap_meta.registry import ItemMetadataRegistry, default_registry


KMA_CROP_WEATHER_BASE_URL = "http://apis.data.go.kr/1360000/FmlandWthrInfoService"
KMA_CROP_WEATHER_OPERATION = "getDayStatistics"
RDA_AGRI_WEATHER_BASE_URL = "http://apis.data.go.kr/1390802/AgriWeather/WeatherObsrInfo/V4/InsttWeather"
RDA_AGRI_WEATHER_OPERATION = "getWeatherMonDayList4"


class DataGoKrWeatherConnector(WeatherConnector):
    def __init__(
        self,
        service_name: str,
        base_url: str,
        operation_path: str = "",
        registry: ItemMetadataRegistry | None = None,
        api_key: str | None = None,
        default_params: dict[str, Any] | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.operation_path = operation_path
        self.service = DataGoKrService(
            name=service_name,
            base_url=base_url,
            default_params=default_params
            or {
                "dataType": os.getenv("DATA_GO_KR_WEATHER_DATA_TYPE", "JSON"),
                "type": os.getenv("DATA_GO_KR_WEATHER_TYPE", "json"),
            },
            api_key_param=os.getenv("DATA_GO_KR_KEY_PARAM", "serviceKey"),
        )
        self.client = DataGoKrClient(api_key=api_key or os.getenv(DATA_GO_KR_API_KEY_ENV))

    def build_params(self, item_code: str, target_date: date) -> dict[str, Any]:
        return {
            os.getenv("DATA_GO_KR_WEATHER_ITEM_PARAM", "item_code"): item_code,
            os.getenv("DATA_GO_KR_WEATHER_DATE_PARAM", "date"): target_date.strftime("%Y%m%d"),
        }

    def fetch_weather(self, item_code: str, target_date: date) -> list[WeatherFeature]:
        if not self.service.base_url:
            return []

        payload = self.client.get(
            self.service,
            self.operation_path,
            **self.build_params(item_code, target_date),
        )
        if isinstance(payload, str) and payload.lstrip().startswith("<"):
            payload = _xml_to_payload(payload)
        return normalize_weather_rows(
            payload,
            item_code=item_code,
            default_date=target_date,
            source=self.service.name,
        )


class CropMainAreaWeatherConnector(DataGoKrWeatherConnector):
    """KMA crop main-area weather connector.

    This API requires external KMA mapping codes per item/region:
    AREA_ID and PA_CROP_SPE_ID. Until those are added to metadata, the
    connector returns no live rows instead of making invalid calls.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            service_name="기상청 작물별 농업주산지 상세날씨 조회서비스",
            base_url=os.getenv("KMA_CROP_WEATHER_BASE_URL", KMA_CROP_WEATHER_BASE_URL),
            operation_path=os.getenv("KMA_CROP_WEATHER_OPERATION", KMA_CROP_WEATHER_OPERATION),
            **kwargs,
        )

    def build_param_sets(self, item_code: str, target_date: date) -> list[dict[str, Any]]:
        item = self.registry.get_item(item_code)
        mappings = item.get("external_mappings", {}).get("kma_crop_weather", {})
        crop_spe_id = mappings.get("pa_crop_spe_id")
        area_ids = mappings.get("area_ids", [])
        area_mappings = mappings.get("area_mappings", [])

        pairs: list[tuple[str, str]] = []
        if area_mappings:
            pairs = [
                (str(row["area_id"]), str(row.get("pa_crop_spe_id") or crop_spe_id))
                for row in area_mappings
                if row.get("area_id") and (row.get("pa_crop_spe_id") or crop_spe_id)
            ]
        elif crop_spe_id and area_ids:
            pairs = [(str(area_id), str(crop_spe_id)) for area_id in area_ids]

        deduped_pairs = list(dict.fromkeys(pairs))
        if not deduped_pairs:
            return []

        return [
            {
                "pageNo": 1,
                "numOfRows": 10,
                "dataType": "JSON",
                os.getenv("KMA_CROP_WEATHER_START_DATE_PARAM", "ST_YMD"): target_date.strftime("%Y%m%d"),
                os.getenv("KMA_CROP_WEATHER_END_DATE_PARAM", "ED_YMD"): target_date.strftime("%Y%m%d"),
                os.getenv("KMA_CROP_WEATHER_AREA_PARAM", "AREA_ID"): area_id,
                os.getenv("KMA_CROP_WEATHER_CROP_PARAM", "PA_CROP_SPE_ID"): pair_crop_spe_id,
            }
            for area_id, pair_crop_spe_id in deduped_pairs
        ]

    def fetch_weather(self, item_code: str, target_date: date) -> list[WeatherFeature]:
        param_sets = self.build_param_sets(item_code, target_date)
        if not param_sets:
            return []

        features: list[WeatherFeature] = []
        for params in param_sets:
            payload = self.client.get(self.service, self.operation_path, **params)
            if public_api_error(payload):
                continue
            features.extend(
                normalize_weather_rows(
                    payload,
                    item_code=item_code,
                    default_date=target_date,
                    source=self.service.name,
                )
            )
        return features


class RdaAgriWeatherConnector(DataGoKrWeatherConnector):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            service_name="농촌진흥청 국립농업과학원 농업기상 상세 관측데이터",
            base_url=os.getenv("RDA_AGRI_WEATHER_BASE_URL") or RDA_AGRI_WEATHER_BASE_URL,
            operation_path=os.getenv("RDA_AGRI_WEATHER_OPERATION") or RDA_AGRI_WEATHER_OPERATION,
            default_params={},
            **kwargs,
        )

    def build_params(self, item_code: str, target_date: date) -> dict[str, Any]:
        params = {
            "Page_No": 1,
            "Page_Size": int(os.getenv("RDA_AGRI_WEATHER_PAGE_SIZE", "100")),
            "search_Year": f"{target_date:%Y}",
            "search_Month": f"{target_date:%m}",
        }
        spot_code = os.getenv("RDA_AGRI_WEATHER_OBSR_SPOT_CD")
        spot_name = os.getenv("RDA_AGRI_WEATHER_OBSR_SPOT_NM")
        if spot_code:
            params["obsr_Spot_Cd"] = spot_code
        if spot_name:
            params["obsr_Spot_Nm"] = spot_name
        return params


def normalize_weather_rows(
    payload: Any,
    item_code: str,
    default_date: date,
    source: str,
) -> list[WeatherFeature]:
    if public_api_error(payload):
        return []

    features: list[WeatherFeature] = []
    for row in extract_rows(payload):
        row_item_code = first_present(row, "item_code", "itemCode", "cropCode", "paCropName", "paCropSpeId")
        if row_item_code and str(row_item_code) != item_code:
            if any(key in row for key in ("item_code", "itemCode", "cropCode")):
                continue

        base_date = parse_date(
            first_present(row, "base_date", "date", "ymd", "tm", "obsrDe", "date_Time"),
            default=default_date,
        )
        region_code = first_present(row, "region_code", "regionCode", "areaId", "areaCd", "stnId", "AREA_ID")
        region_name = first_present(row, "region_name", "regionName", "areaName", "areaNm", "stnNm", "AREA_NM")

        features.append(
            WeatherFeature(
                item_code=item_code,
                region_code=str(region_code or region_name or ""),
                base_date=base_date,
                temperature=parse_float(
                    first_present(row, "temperature", "temp", "ta", "avgTa", "dayAvgTa", "AVG_TA", "MIN_TA", "MAX_TA", "tmprt_150")
                ),
                rainfall=parse_float(first_present(row, "rainfall", "rain", "rn", "sumRn", "daySumRn", "SUM_RN", "rain_1hr", "rainfall_1hr")),
                humidity=parse_float(first_present(row, "humidity", "hm", "avgRhm", "dayAvgRhm", "AVG_RHM", "hd_150")),
                wind_speed=parse_float(first_present(row, "wind_speed", "ws", "avgWs", "dayAvgWs", "AVG_WS", "wnd_150")),
                sunshine=parse_float(first_present(row, "sunshine", "ss", "sumSsHr", "daySumSs", "SUM_SS_HR", "srqty")),
                source=source,
                raw=row,
            )
        )
    return features


def _xml_to_payload(text: str) -> dict[str, Any]:
    root = ET.fromstring(text)
    return _element_to_dict(root)


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    children = list(element)
    if not children:
        return element.text.strip() if element.text else ""

    payload: dict[str, Any] = {}
    grouped: dict[str, list[Any]] = {}
    for child in children:
        key = child.tag.rsplit("}", 1)[-1]
        grouped.setdefault(key, []).append(_element_to_dict(child))

    for key, values in grouped.items():
        payload[key] = values[0] if len(values) == 1 else values
    return payload
