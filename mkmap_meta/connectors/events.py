from __future__ import annotations

import os
from datetime import date
from typing import Any

from mkmap_meta.connectors.base import EventConnector
from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV, DataGoKrClient, DataGoKrService
from mkmap_meta.connectors.normalizers import extract_rows, first_present, parse_date, parse_float, public_api_error
from mkmap_meta.models import EventFeature


KMA_WEATHER_ALERT_BASE_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService"
KMA_WEATHER_ALERT_OPERATION = "getWthrWrnList"
KMA_IMPACT_FORECAST_BASE_URL = "http://apis.data.go.kr/1360000/ImpactInfoServiceV2"
KMA_IMPACT_FORECAST_OPERATION = "getHWImpactValueV2"
KMA_TYPHOON_BASE_URL = "http://apis.data.go.kr/1360000/TyphoonInfoService"
KMA_TYPHOON_OPERATION = "getTyphoonInfoList"
KMA_MIDTERM_FORECAST_BASE_URL = "http://apis.data.go.kr/1360000/MidFcstInfoService"
KMA_MIDTERM_FORECAST_OPERATION = "getMidFcst"
KMA_SATELLITE_BASE_URL = "http://apis.data.go.kr/1360000/WthrSatlitInfoService"
KMA_SATELLITE_OPERATION = "getGk2aIrAll"
KMA_WEATHER_CHART_BASE_URL = "http://apis.data.go.kr/1360000/WthrChartInfoService"
KMA_WEATHER_CHART_OPERATION = "getSurfaceChart"


def _env_or_default(name: str, default: str) -> str:
    return os.getenv(name) or default


def _event_level_score(level: Any) -> float | None:
    if level is None:
        return None
    return {
        "\uad00\uc2ec": 0.2,
        "\uc8fc\uc758": 0.45,
        "\uacbd\uace0": 0.7,
        "\uc704\ud5d8": 1.0,
    }.get(str(level))


class DataGoKrEventConnector(EventConnector):
    def __init__(
        self,
        service_name: str,
        event_type: str,
        base_url: str,
        operation_path: str = "",
        date_param: str = "date",
        api_key: str | None = None,
        default_params: dict[str, Any] | None = None,
    ) -> None:
        self.event_type = event_type
        self.operation_path = operation_path
        self.date_param = date_param
        self.service = DataGoKrService(
            name=service_name,
            base_url=base_url,
            default_params=default_params
            or {
                "dataType": os.getenv("DATA_GO_KR_EVENT_DATA_TYPE", "JSON"),
                "type": os.getenv("DATA_GO_KR_EVENT_TYPE", "json"),
            },
            api_key_param=os.getenv("DATA_GO_KR_KEY_PARAM", "serviceKey"),
        )
        self.client = DataGoKrClient(api_key=api_key or os.getenv(DATA_GO_KR_API_KEY_ENV))

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            self.date_param: target_date.strftime("%Y%m%d"),
        }

    def fetch_events(self, target_date: date) -> list[EventFeature]:
        if not self.service.base_url:
            return []

        payload = self.fetch_payload(target_date)
        return self.normalize_payload(payload, target_date)

    def normalize_payload(self, payload: Any, target_date: date) -> list[EventFeature]:
        return normalize_event_rows(
            payload,
            default_date=target_date,
            event_type=self.event_type,
            source=self.service.name,
        )

    def fetch_payload(self, target_date: date) -> Any:
        return self.client.get(
            self.service,
            self.operation_path,
            **self.build_params(target_date),
        )


class WeatherAlertConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            service_name="기상청 기상특보 조회서비스",
            event_type="weather_alert",
            base_url=os.getenv("KMA_WEATHER_ALERT_BASE_URL", KMA_WEATHER_ALERT_BASE_URL),
            operation_path=os.getenv("KMA_WEATHER_ALERT_OPERATION", KMA_WEATHER_ALERT_OPERATION),
            date_param=os.getenv("KMA_WEATHER_ALERT_FROM_PARAM", "fromTmFc"),
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        from_value = f"{target_date:%Y%m%d}0000"
        to_value = f"{target_date:%Y%m%d}2359"
        return {
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            os.getenv("KMA_WEATHER_ALERT_FROM_PARAM", "fromTmFc"): from_value,
            os.getenv("KMA_WEATHER_ALERT_TO_PARAM", "toTmFc"): to_value,
            os.getenv("KMA_WEATHER_ALERT_STN_PARAM", "stnId"): os.getenv("KMA_WEATHER_ALERT_DEFAULT_STN_ID", "0"),
        }


class ImpactForecastConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        date_param = _env_or_default("KMA_IMPACT_FORECAST_DATE_PARAM", "tm")
        if date_param in {"date", "tmFc"}:
            date_param = "tm"

        super().__init__(
            service_name="기상청 영향예보 조회서비스",
            event_type="impact_forecast",
            base_url=_env_or_default("KMA_IMPACT_FORECAST_BASE_URL", KMA_IMPACT_FORECAST_BASE_URL),
            operation_path=_env_or_default("KMA_IMPACT_FORECAST_OPERATION", KMA_IMPACT_FORECAST_OPERATION),
            date_param=date_param,
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            self.date_param: f"{target_date:%Y%m%d}",
            "efSn": os.getenv("KMA_IMPACT_FORECAST_DEFAULT_EF_SN", "3"),
        }


class TyphoonConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            service_name="기상청 태풍정보 조회서비스",
            event_type="typhoon",
            base_url=os.getenv("KMA_TYPHOON_BASE_URL", KMA_TYPHOON_BASE_URL),
            operation_path=os.getenv("KMA_TYPHOON_LIST_OPERATION", KMA_TYPHOON_OPERATION),
            date_param=os.getenv("KMA_TYPHOON_DATE_PARAM", "tmFc"),
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            self.date_param: f"{target_date:%Y%m%d}0000",
        }


class MidtermForecastConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            service_name="기상청 중기예보 조회서비스",
            event_type="midterm_forecast",
            base_url=os.getenv("KMA_MIDTERM_FORECAST_BASE_URL", KMA_MIDTERM_FORECAST_BASE_URL),
            operation_path=os.getenv("KMA_MIDTERM_FORECAST_OPERATION", KMA_MIDTERM_FORECAST_OPERATION),
            date_param=os.getenv("KMA_MIDTERM_FORECAST_DATE_PARAM", "tmFc"),
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            os.getenv("KMA_MIDTERM_FORECAST_STN_PARAM", "stnId"): os.getenv("KMA_MIDTERM_FORECAST_DEFAULT_STN_ID", "108"),
            self.date_param: f"{target_date:%Y%m%d}0600",
        }


class SatelliteConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        date_param = _env_or_default("KMA_SATELLITE_DATE_PARAM", "dateTime")
        if date_param == "date":
            date_param = "dateTime"

        super().__init__(
            service_name="기상청 위성자료(경량화) 조회서비스",
            event_type="satellite",
            base_url=_env_or_default("KMA_SATELLITE_BASE_URL", KMA_SATELLITE_BASE_URL),
            operation_path=_env_or_default("KMA_SATELLITE_OPERATION", KMA_SATELLITE_OPERATION),
            date_param=date_param,
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            self.date_param: f"{target_date:%Y%m%d}0000",
            os.getenv("KMA_SATELLITE_WAVE_TYPE_PARAM", "waveType"): os.getenv("KMA_SATELLITE_DEFAULT_WAVE_TYPE", "087"),
            os.getenv("KMA_SATELLITE_UNIT_TYPE_PARAM", "unitType"): os.getenv("KMA_SATELLITE_DEFAULT_UNIT_TYPE", "R"),
        }


class WeatherChartConnector(DataGoKrEventConnector):
    def __init__(self, **kwargs: Any) -> None:
        date_param = _env_or_default("KMA_WEATHER_CHART_DATE_PARAM", "time")
        if date_param == "date":
            date_param = "time"

        super().__init__(
            service_name="기상청 일기도 조회서비스",
            event_type="weather_chart",
            base_url=_env_or_default("KMA_WEATHER_CHART_BASE_URL", KMA_WEATHER_CHART_BASE_URL),
            operation_path=_env_or_default("KMA_WEATHER_CHART_OPERATION", KMA_WEATHER_CHART_OPERATION),
            date_param=date_param,
            **kwargs,
        )

    def build_params(self, target_date: date) -> dict[str, Any]:
        return {
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            os.getenv("KMA_WEATHER_CHART_CODE_PARAM", "code"): os.getenv("KMA_WEATHER_CHART_DEFAULT_CODE", "24"),
            self.date_param: f"{target_date:%Y%m%d}",
        }


def normalize_event_rows(
    payload: Any,
    default_date: date,
    event_type: str,
    source: str,
) -> list[EventFeature]:
    if public_api_error(payload):
        return []

    features: list[EventFeature] = []
    for row in extract_rows(payload):
        base_date = parse_date(
            first_present(row, "base_date", "date", "tm", "tmFc", "tmEf", "announceTime"),
            default=default_date,
        )
        region_code = first_present(row, "region_code", "regionCode", "areaCd", "stnId", "areaCode", "regId")
        level = first_present(row, "level", "warnLevel", "severity", "warningLevel", "cmd", "wrnLvl", "value")
        title = first_present(row, "title", "event", "warnVar", "phenomenon", "titleKor", "wrn", "wrnVar", "clsfc")
        description = first_present(row, "description", "desc", "content", "message", "t6", "other", "regName")
        severity_score = parse_float(first_present(row, "severity_score", "score", "risk")) or _event_level_score(level)

        features.append(
            EventFeature(
                region_code=str(region_code) if region_code is not None else None,
                base_date=base_date,
                event_type=event_type,
                level=str(level) if level is not None else None,
                title=str(title) if title is not None else None,
                description=str(description) if description is not None else None,
                severity_score=severity_score,
                source=source,
                raw=row,
            )
        )
    return features
