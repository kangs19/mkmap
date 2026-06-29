from __future__ import annotations

import os
from typing import Any

from mkmap_meta.connectors.base import ProductionConnector
from mkmap_meta.connectors.kosis import KOSIS_PARAMETER_DATA_URL, KosisClient, KosisTable
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
            base_url=base_url or os.getenv("KOSIS_PRODUCTION_BASE_URL") or KOSIS_PARAMETER_DATA_URL,
            org_id=os.getenv("KOSIS_PRODUCTION_ORG_ID") or "101",
            tbl_id=os.getenv("KOSIS_PRODUCTION_TBL_ID"),
            default_params={
                "prdSe": os.getenv("KOSIS_PRODUCTION_PERIOD_TYPE") or "Y",
            },
        )
        self.client = KosisClient(api_key=api_key)
        self.item_param = _normalize_kosis_item_param(os.getenv("KOSIS_PRODUCTION_ITEM_PARAM"))
        self.year_param = os.getenv("KOSIS_PRODUCTION_YEAR_PARAM") or "startPrdDe"

    def fetch_production(self, item_code: str, year: int) -> list[ProductionFeature]:
        mapping = self.registry.get_item(item_code).get("external_mappings", {}).get("kosis_production", {})
        if not mapping:
            return []

        payload = self.client.get(
            self.table,
            **{
                self.item_param: "ALL",
                "objL1": "ALL",
                self.year_param: year,
                "endPrdDe": year,
                "orgId": mapping.get("org_id") or self.table.org_id,
                "tblId": mapping.get("tbl_id") or self.table.tbl_id,
            },
        )
        return normalize_kosis_production_rows(
            payload,
            item_code=item_code,
            item_name=mapping.get("item_name") or _korean_item_name(item_code),
            default_year=year,
        )


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


def normalize_kosis_production_rows(
    payload: Any,
    item_code: str,
    item_name: str,
    default_year: int,
) -> list[ProductionFeature]:
    grouped: dict[tuple[str, str, int], dict[str, Any]] = {}

    for row in extract_rows(payload):
        metric_name = str(first_present(row, "ITM_NM", "itmNm", "item_name") or "")
        if not _is_target_kosis_metric(metric_name, item_name):
            continue

        value = parse_float(first_present(row, "DT", "value"))
        if value is None:
            continue

        year = _parse_year(first_present(row, "PRD_DE", "year"), default_year)
        region_code = str(first_present(row, "C1", "region_code") or "")
        region_name = str(first_present(row, "C1_NM", "region_name") or region_code)
        if region_name in {"계", "전국", "Total"} or region_code in {"00", "P00000"}:
            continue

        key = (region_code, region_name, year)
        bucket = grouped.setdefault(
            key,
            {
                "region_code": region_code,
                "region_name": region_name,
                "year": year,
                "cultivation_area": None,
                "production_volume": None,
                "raw_rows": [],
            },
        )
        if metric_name.endswith(":면적") or metric_name.endswith(":Area"):
            bucket["cultivation_area"] = float(bucket["cultivation_area"] or 0) + value
        elif metric_name.endswith(":생산량") or metric_name.endswith(":Production"):
            bucket["production_volume"] = float(bucket["production_volume"] or 0) + value
        bucket["raw_rows"].append(row)

    total_volume = sum(float(row["production_volume"] or 0) for row in grouped.values())
    total_area = sum(float(row["cultivation_area"] or 0) for row in grouped.values())
    features: list[ProductionFeature] = []

    for row in grouped.values():
        volume = row["production_volume"]
        area = row["cultivation_area"]
        share = None
        if volume is not None and total_volume > 0:
            share = float(volume) / total_volume
        elif area is not None and total_area > 0:
            share = float(area) / total_area

        features.append(
            ProductionFeature(
                item_code=item_code,
                region_code=row["region_code"],
                region_name=row["region_name"],
                year=row["year"],
                cultivation_area=area,
                production_volume=volume,
                production_share=share,
                source="kosis",
                raw={"rows": row["raw_rows"]},
            )
        )

    return sorted(features, key=lambda feature: feature.production_share or 0, reverse=True)


def normalize_production_rows(payload: Any, item_code: str, default_year: int) -> list[ProductionFeature]:
    """Generic production normalizer retained for non-KOSIS tabular payloads."""

    features: list[ProductionFeature] = []
    rows = extract_rows(payload)
    total_volume = 0.0
    pending: list[ProductionFeature] = []

    for row in rows:
        row_item_code = first_present(row, "item_code", "itemCode", "itemCd", "품목코드", "C1_NM", "ITM_NM")
        if row_item_code and str(row_item_code) not in {item_code, _korean_item_name(item_code)}:
            if any(key in row for key in ("item_code", "itemCode", "itemCd", "품목코드")):
                continue

        year = _parse_year(first_present(row, "year", "PRD_DE", "prdDe", "연도"), default_year)
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

    if total_volume <= 0:
        return pending

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
    return features


def _is_target_kosis_metric(metric_name: str, item_name: str) -> bool:
    if item_name not in metric_name:
        return False
    if "10a당" in metric_name:
        return False
    return metric_name.endswith(":면적") or metric_name.endswith(":생산량")


def _parse_year(value: Any, default_year: int) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default_year


def _normalize_kosis_item_param(value: str | None) -> str:
    if value in (None, "", "item_code", "itemCode", "itemCd"):
        return "itmId"
    return value


def _korean_item_name(item_code: str) -> str:
    return {
        "cabbage": "배추",
        "radish": "무",
        "onion": "양파",
        "green_onion": "대파",
        "garlic": "마늘",
    }.get(item_code, item_code)
