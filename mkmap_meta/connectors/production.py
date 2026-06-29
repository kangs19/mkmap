from __future__ import annotations

import os
from datetime import date
from typing import Any

from mkmap_meta.connectors.base import ProductionConnector
from mkmap_meta.connectors.kosis import KosisClient, KosisTable
from mkmap_meta.connectors.normalizers import extract_rows, first_present, parse_float
from mkmap_meta.models import ProductionFeature
from mkmap_meta.registry import ItemMetadataRegistry, default_registry


class KosisProductionConnector(ProductionConnector):
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        registry: ItemMetadataRegistry | None = None,
    ) -> None:
        self.registry = registry or default_registry()
        self.table = KosisTable(
            name="KOSIS crop production statistics",
            base_url=base_url or os.getenv("KOSIS_PRODUCTION_BASE_URL", ""),
            org_id=os.getenv("KOSIS_PRODUCTION_ORG_ID"),
            tbl_id=os.getenv("KOSIS_PRODUCTION_TBL_ID"),
            default_params={
                "prdSe": os.getenv("KOSIS_PRODUCTION_PERIOD_TYPE", "Y"),
            },
        )
        self.client = KosisClient(api_key=api_key)
        self.item_param = os.getenv("KOSIS_PRODUCTION_ITEM_PARAM", "item_code")
        self.year_param = os.getenv("KOSIS_PRODUCTION_YEAR_PARAM", "startPrdDe")

    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        if not self.table.base_url:
            return []

        payload = self.client.get(
            self.table,
            **{
                self.item_param: item_code,
                self.year_param: year,
                "endPrdDe": year,
            },
        )
        return normalize_production_rows(payload, item_code=item_code, default_year=year)


class ManualProductionConnector(ProductionConnector):
    """Fallback connector using production_profile.manual_regions."""

    def __init__(self, registry: ItemMetadataRegistry | None = None) -> None:
        self.registry = registry or default_registry()

    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        item = self.registry.get_item(item_code)
        regions = item["production_profile"]["manual_regions"]
        return [
            ProductionFeature(
                item_code=item_code,
                region_code=region["region_code"],
                region_name=region["region_name"],
                year=year,
                production_share=region["base_weight"],
                source="manual_region_weight",
                raw=region,
            )
            for region in regions
        ]


def normalize_production_rows(payload: Any, item_code: str, default_year: int) -> list[ProductionFeature]:
    features: list[ProductionFeature] = []
    rows = extract_rows(payload)
    total_volume = 0.0
    pending: list[ProductionFeature] = []

    for row in rows:
        row_item_code = first_present(row, "item_code", "itemCode", "itemCd", "품목코드", "C1_NM", "ITM_NM")
        if row_item_code and str(row_item_code) not in {item_code, _korean_item_name(item_code)}:
            # KOSIS rows may not expose our internal item code. If a row clearly
            # belongs to another item, skip it; otherwise keep it for configured tables.
            if any(key in row for key in ("item_code", "itemCode", "itemCd", "품목코드")):
                continue

        year_value = first_present(row, "year", "PRD_DE", "prdDe", "연도")
        try:
            year = int(year_value) if year_value is not None else default_year
        except ValueError:
            year = default_year

        region_code = first_present(row, "region_code", "regionCode", "C2", "C2_ID", "지역코드")
        region_name = first_present(row, "region_name", "regionName", "C2_NM", "지역", "시도")
        cultivation_area = parse_float(first_present(row, "cultivation_area", "area", "재배면적"))
        production_volume = parse_float(first_present(row, "production_volume", "volume", "DT", "생산량"))
        production_share = parse_float(first_present(row, "production_share", "share", "비중"))

        if production_volume:
            total_volume += production_volume

        pending.append(
            ProductionFeature(
                item_code=item_code,
                region_code=str(region_code) if region_code is not None else str(region_name or ""),
                region_name=str(region_name or region_code or ""),
                year=year,
                cultivation_area=cultivation_area,
                production_volume=production_volume,
                production_share=production_share,
                source="kosis",
                raw=row,
            )
        )

    if total_volume > 0:
        for feature in pending:
            share = feature.production_share
            if share is None and feature.production_volume is not None:
                share = feature.production_volume / total_volume
            features.append(
                ProductionFeature(
                    item_code=feature.item_code,
                    region_code=feature.region_code,
                    region_name=feature.region_name,
                    year=feature.year,
                    cultivation_area=feature.cultivation_area,
                    production_volume=feature.production_volume,
                    production_share=share,
                    source=feature.source,
                    raw=feature.raw,
                )
            )
    else:
        features = pending

    return features


def _korean_item_name(item_code: str) -> str:
    return {
        "cabbage": "배추",
        "radish": "무",
        "onion": "양파",
        "green_onion": "대파",
        "garlic": "마늘",
    }.get(item_code, item_code)

