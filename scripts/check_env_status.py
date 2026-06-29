from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded


ENV_GROUPS = {
    "keys": ["DATA_GO_KR_API_KEY", "KAMIS_API_KEY", "KAMIS_CERT_ID", "KOSIS_API_KEY"],
    "kma_core_defaults": [
        "KMA_CROP_WEATHER_BASE_URL",
        "KMA_CROP_WEATHER_OPERATION",
        "KMA_WEATHER_ALERT_BASE_URL",
        "KMA_WEATHER_ALERT_OPERATION",
        "KMA_TYPHOON_BASE_URL",
        "KMA_TYPHOON_OPERATION",
        "KMA_TYPHOON_LIST_OPERATION",
        "KMA_MIDTERM_FORECAST_BASE_URL",
        "KMA_MIDTERM_FORECAST_OPERATION",
    ],
    "price": [
        "KAMIS_PRICE_BASE_URL",
        "KAMIS_PRICE_ACTION",
        "KAMIS_PRODUCT_CLASSES",
        "AT_REGIONAL_PRICE_BASE_URL",
        "AT_MARKET_SETTLEMENT_BASE_URL",
    ],
    "production": ["KOSIS_PRODUCTION_BASE_URL", "KOSIS_PRODUCTION_ORG_ID", "KOSIS_PRODUCTION_TBL_ID"],
}

CODE_DEFAULTS = {
    "KMA_CROP_WEATHER_BASE_URL": "http://apis.data.go.kr/1360000/FmlandWthrInfoService",
    "KMA_CROP_WEATHER_OPERATION": "getDayStatistics",
    "KMA_WEATHER_ALERT_BASE_URL": "http://apis.data.go.kr/1360000/WthrWrnInfoService",
    "KMA_WEATHER_ALERT_OPERATION": "getWthrWrnList",
    "KMA_TYPHOON_BASE_URL": "http://apis.data.go.kr/1360000/TyphoonInfoService",
    "KMA_TYPHOON_OPERATION": "getTyphoonInfoList",
    "KMA_TYPHOON_LIST_OPERATION": "getTyphoonInfoList",
    "KMA_MIDTERM_FORECAST_BASE_URL": "http://apis.data.go.kr/1360000/MidFcstInfoService",
    "KMA_MIDTERM_FORECAST_OPERATION": "getMidFcst",
    "KAMIS_PRICE_BASE_URL": "https://www.kamis.or.kr/service/price/xml.do",
    "KAMIS_PRICE_ACTION": "periodProductList",
    "KAMIS_PRODUCT_CLASSES": "01,02",
    "KOSIS_PRODUCTION_BASE_URL": "https://kosis.kr/openapi/Param/statisticsParameterData.do",
    "KOSIS_PRODUCTION_ORG_ID": "101",
}


def status(env_name: str) -> dict[str, object]:
    value = os.getenv(env_name)
    default = CODE_DEFAULTS.get(env_name)
    return {
        "name": env_name,
        "configured": bool(value),
        "code_default_available": bool(default),
        "value_preview": "***" if value and ("KEY" in env_name or "API" in env_name) else (value or None),
        "default_preview": default,
    }


def main() -> int:
    ensure_env_loaded()
    payload = {
        group: [status(env_name) for env_name in env_names]
        for group, env_names in ENV_GROUPS.items()
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
