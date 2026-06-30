from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.service_catalog import load_service_catalog


SAMPLE_DATE = date(2026, 6, 29)


def sample_params(service_code: str) -> dict[str, Any]:
    if service_code == "kma_crop_weather":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "ST_YMD": SAMPLE_DATE.strftime("%Y%m%d"),
            "ED_YMD": SAMPLE_DATE.strftime("%Y%m%d"),
            "AREA_ID": "<each metadata.external_mappings.kma_crop_weather.area_ids[]>",
            "PA_CROP_SPE_ID": "<metadata.external_mappings.kma_crop_weather.pa_crop_spe_id>",
        }
    if service_code == "rda_agri_weather":
        return {
            "serviceKey": "***",
            "Page_No": 1,
            "Page_Size": 100,
            "search_Year": f"{SAMPLE_DATE:%Y}",
            "search_Month": f"{SAMPLE_DATE:%m}",
            "obsr_Spot_Cd": "<optional RDA observation spot code>",
        }
    if service_code == "kma_weather_alert":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            "fromTmFc": f"{SAMPLE_DATE:%Y%m%d}0000",
            "toTmFc": f"{SAMPLE_DATE:%Y%m%d}2359",
            "stnId": "0",
        }
    if service_code == "at_regional_price":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 100,
            "returnType": "JSON",
            "cond[exmn_ymd::GTE]": SAMPLE_DATE.strftime("%Y%m%d"),
            "cond[exmn_ymd::LTE]": SAMPLE_DATE.strftime("%Y%m%d"),
            "cond[sgg_cd::EQ]": "1101",
            "cond[ctgry_cd::EQ]": "200",
            "cond[item_cd::EQ]": "211",
            "cond[vrty_cd::EQ]": "01",
            "cond[grd_cd::EQ]": "04",
        }
    if service_code == "at_market_settlement":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 100,
            "returnType": "json",
            "cond[trd_clcln_ymd::EQ]": SAMPLE_DATE.isoformat(),
            "cond[whsl_mrkt_cd::EQ]": "110001",
            "cond[gds_lclsf_cd::EQ]": "12",
            "cond[gds_mclsf_cd::EQ]": "01",
            "cond[gds_sclsf_cd::EQ]": "02",
        }
    if service_code == "kma_typhoon":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            "tmFc": f"{SAMPLE_DATE:%Y%m%d}0000",
        }
    if service_code == "kma_midterm_forecast":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "stnId": "108",
            "tmFc": f"{SAMPLE_DATE:%Y%m%d}0600",
        }
    if service_code == "kma_impact_forecast":
        return {
            "serviceKey": "***",
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "tm": f"{SAMPLE_DATE:%Y%m%d}",
            "efSn": "3",
        }
    return {}


def main() -> int:
    previews = []
    for service in load_service_catalog():
        if not service.base_url or not service.operation:
            continue
        previews.append(
            {
                "provider": service.provider,
                "code": service.code,
                "display_name": service.display_name,
                "url": f"{service.base_url.rstrip('/')}/{service.operation.lstrip('/')}",
                "status": service.status,
                "sample_params": sample_params(service.code),
                "notes": service.notes,
            }
        )

    print(json.dumps(previews, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
