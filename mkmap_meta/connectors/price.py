from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any
from xml.etree import ElementTree as ET

from mkmap_meta.connectors.base import PriceConnector
from mkmap_meta.connectors.data_go_kr import DATA_GO_KR_API_KEY_ENV, DataGoKrClient, DataGoKrService
from mkmap_meta.connectors.http import SimpleHttpClient
from mkmap_meta.connectors.normalizers import extract_rows, first_present, parse_date, parse_float
from mkmap_meta.models import PriceFeature
from mkmap_meta.registry import ItemMetadataRegistry, default_registry


KAMIS_PRICE_BASE_URL = "https://www.kamis.or.kr/service/price/xml.do"
KAMIS_PRICE_ACTION = "periodProductList"
AT_REGIONAL_PRICE_BASE_URL = "http://apis.data.go.kr/B552845/perRegion"
AT_REGIONAL_PRICE_OPERATION = "price"
AT_MARKET_SETTLEMENT_BASE_URL = "http://apis.data.go.kr/B552845/katSale"
AT_MARKET_SETTLEMENT_OPERATION = "trades"


class KamisPriceConnector(PriceConnector):
    """KAMIS periodProductList connector driven by item metadata mappings."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        cert_id: str | None = None,
        registry: ItemMetadataRegistry | None = None,
        http: SimpleHttpClient | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv("KAMIS_PRICE_BASE_URL") or KAMIS_PRICE_BASE_URL
        self.action = os.getenv("KAMIS_PRICE_ACTION") or KAMIS_PRICE_ACTION
        self.api_key = api_key or os.getenv("KAMIS_API_KEY")
        self.cert_id = cert_id or os.getenv("KAMIS_CERT_ID") or os.getenv("KAMIS_API_ID") or "mkmap"
        self.return_type = os.getenv("KAMIS_RETURN_TYPE_VALUE") or "json"
        self.product_classes = _csv(os.getenv("KAMIS_PRODUCT_CLASSES") or "01,02")
        self.include_secondary_variants = os.getenv("KAMIS_INCLUDE_SECONDARY_VARIANTS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        self.registry = registry or default_registry()
        # KAMIS API (kamis.or.kr) causes SSLv3 handshake failures from some hosting IPs.
        # verify_ssl=False is required for Railway/cloud deployments.
        self.http = http or SimpleHttpClient(verify_ssl=False)

    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        if not self.base_url or not self.api_key or not self.cert_id:
            return []

        mapping = self._mapping_for(item_code)
        if not mapping:
            return []

        start_date = target_date - timedelta(days=max(days_back - 1, 0))
        features: list[PriceFeature] = []
        for product_cls in _mapping_product_classes(mapping, self.product_classes):
            for variant in self._variants(mapping):
                params = self._params(mapping, variant, product_cls, start_date, target_date)
                payload = self.fetch_payload(params)
                features.extend(
                    normalize_kamis_price_rows(
                        payload,
                        item_code=item_code,
                        default_date=target_date,
                        source="kamis",
                        product_cls=product_cls,
                        variant=variant,
                    )
                )
        return _dedupe_price_features(features)

    def fetch_payload(self, params: dict[str, Any]) -> Any:
        text = self.http.get(self.base_url, params=params).text
        stripped = text.strip()
        if not stripped:
            return {}
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)
        if stripped.startswith("<"):
            return _xml_to_payload(stripped)
        return {"raw_text": stripped}

    def _mapping_for(self, item_code: str) -> dict[str, Any]:
        item = self.registry.get_item(item_code)
        return item.get("external_mappings", {}).get("kamis_price", {})

    def _variants(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        variants = [variant for variant in mapping.get("variants", []) if isinstance(variant, dict)]
        if self.include_secondary_variants:
            return variants
        primary = [variant for variant in variants if variant.get("primary", True)]
        return primary or variants

    def _params(
        self,
        mapping: dict[str, Any],
        variant: dict[str, Any],
        product_cls: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        return {
            "action": self.action,
            "p_product_cls": product_cls,
            "p_cert_key": self.api_key,
            "p_cert_id": self.cert_id,
            "p_returntype": self.return_type,
            "p_startday": start_date.isoformat(),
            "p_endday": end_date.isoformat(),
            "p_itemcategorycode": mapping.get("itemcategorycode"),
            "p_itemcode": mapping.get("itemcode"),
            "p_kindcode": variant.get("kindcode"),
            "p_convert_kg_yn": os.getenv("KAMIS_CONVERT_KG_YN"),
        }


class AtRegionalPriceConnector(PriceConnector):
    """data.go.kr aT regional retail/wholesale price connector."""

    def __init__(
        self,
        base_url: str | None = None,
        operation_path: str | None = None,
        api_key: str | None = None,
        registry: ItemMetadataRegistry | None = None,
        http: SimpleHttpClient | None = None,
    ) -> None:
        base_url = base_url or os.getenv("AT_REGIONAL_PRICE_BASE_URL") or AT_REGIONAL_PRICE_BASE_URL
        self.operation_path = operation_path or os.getenv("AT_REGIONAL_PRICE_OPERATION") or AT_REGIONAL_PRICE_OPERATION
        self.service = DataGoKrService(
            name="한국농수산식품유통공사 지역별 품목별 도소매 가격정보 조회",
            base_url=base_url,
            default_params={
                "returnType": os.getenv("AT_REGIONAL_PRICE_RETURN_TYPE", "JSON"),
            },
        )
        self.client = DataGoKrClient(api_key=api_key or os.getenv(DATA_GO_KR_API_KEY_ENV), http=http)
        self.registry = registry or default_registry()
        self.sgg_cd = os.getenv("AT_REGIONAL_PRICE_DEFAULT_SGG_CD", "1101")
        self.num_rows = int(os.getenv("AT_REGIONAL_PRICE_NUM_ROWS", "100"))

    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        if not self.service.base_url:
            return []
        mapping = self._mapping_for(item_code)
        if not mapping:
            return []

        features: list[PriceFeature] = []
        start_date = target_date - timedelta(days=max(days_back - 1, 0))
        for variant in self._variants(mapping):
            payload = self.client.get(
                self.service,
                self.operation_path,
                **self._params(mapping, variant, start_date, target_date),
            )
            features.extend(
                normalize_at_regional_price_rows(
                    payload,
                    item_code=item_code,
                    default_date=target_date,
                    source="at_regional_price",
                )
            )
        return _dedupe_price_features(features)

    def _mapping_for(self, item_code: str) -> dict[str, Any]:
        item = self.registry.get_item(item_code)
        return item.get("external_mappings", {}).get("kamis_price", {})

    def _variants(self, mapping: dict[str, Any]) -> list[dict[str, Any]]:
        variants = [variant for variant in mapping.get("variants", []) if isinstance(variant, dict)]
        primary = [variant for variant in variants if variant.get("primary", True)]
        return primary or variants or [{}]

    def _params(
        self,
        mapping: dict[str, Any],
        variant: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        params = {
            "pageNo": 1,
            "numOfRows": self.num_rows,
            "cond[exmn_ymd::GTE]": start_date.strftime("%Y%m%d"),
            "cond[exmn_ymd::LTE]": end_date.strftime("%Y%m%d"),
            "cond[sgg_cd::EQ]": os.getenv("AT_REGIONAL_PRICE_SGG_CD", self.sgg_cd),
            "cond[ctgry_cd::EQ]": mapping.get("itemcategorycode"),
            "cond[item_cd::EQ]": mapping.get("itemcode"),
            "cond[vrty_cd::EQ]": variant.get("kindcode"),
            "cond[grd_cd::EQ]": mapping.get("productrankcode"),
        }
        product_cls = os.getenv("AT_REGIONAL_PRICE_PRODUCT_CLS")
        if product_cls:
            params["cond[se_cd::EQ]"] = product_cls
        return {key: value for key, value in params.items() if value not in {None, ""}}


class AtMarketSettlementConnector(PriceConnector):
    """data.go.kr aT public wholesale market settlement connector."""

    def __init__(
        self,
        base_url: str | None = None,
        operation_path: str | None = None,
        api_key: str | None = None,
        registry: ItemMetadataRegistry | None = None,
        http: SimpleHttpClient | None = None,
    ) -> None:
        base_url = base_url or os.getenv("AT_MARKET_SETTLEMENT_BASE_URL") or AT_MARKET_SETTLEMENT_BASE_URL
        self.operation_path = operation_path or os.getenv("AT_MARKET_SETTLEMENT_OPERATION") or AT_MARKET_SETTLEMENT_OPERATION
        self.service = DataGoKrService(
            name="한국농수산식품유통공사 전국 공영도매시장 정산정보",
            base_url=base_url,
            default_params={
                "returnType": os.getenv("AT_MARKET_SETTLEMENT_RETURN_TYPE", "json"),
            },
        )
        self.client = DataGoKrClient(api_key=api_key or os.getenv(DATA_GO_KR_API_KEY_ENV), http=http)
        self.registry = registry or default_registry()
        self.market_code = os.getenv("AT_MARKET_SETTLEMENT_DEFAULT_MARKET_CODE", "110001")
        self.num_rows = int(os.getenv("AT_MARKET_SETTLEMENT_NUM_ROWS", "100"))

    # aT 정산 API는 날짜 하나씩 호출 — 대량 호출 시 429 발생. 최대 90일로 제한.
    _MAX_DAYS_BACK = 90

    def fetch_prices(self, item_code: str, target_date: date, days_back: int = 7) -> list[PriceFeature]:
        import time

        if not self.service.base_url:
            return []

        mapping = self._mapping_for(item_code)
        if not mapping:
            return []

        effective_days = min(days_back, self._MAX_DAYS_BACK)
        features: list[PriceFeature] = []
        for offset in range(effective_days):
            current_date = target_date - timedelta(days=offset)
            payload = self.client.get(
                self.service,
                self.operation_path,
                **self._params(mapping, current_date),
            )
            features.extend(
                normalize_at_market_settlement_rows(
                    payload,
                    item_code=item_code,
                    default_date=current_date,
                    source="at_market_settlement",
                )
            )
            if effective_days > 30:
                time.sleep(0.3)  # 대량 수집 시 rate limit 방어
        return _dedupe_price_features(features)

    def _mapping_for(self, item_code: str) -> dict[str, Any]:
        item = self.registry.get_item(item_code)
        return item.get("external_mappings", {}).get("at_settlement", {})

    def _params(self, mapping: dict[str, Any], target_date: date) -> dict[str, Any]:
        params = {
            "pageNo": 1,
            "numOfRows": self.num_rows,
            "cond[trd_clcln_ymd::EQ]": target_date.isoformat(),
            "cond[whsl_mrkt_cd::EQ]": os.getenv("AT_MARKET_SETTLEMENT_MARKET_CODE") or mapping.get("default_market_code") or self.market_code,
            "cond[gds_lclsf_cd::EQ]": mapping.get("gds_lclsf_cd"),
            "cond[gds_mclsf_cd::EQ]": mapping.get("gds_mclsf_cd"),
            "cond[gds_sclsf_cd::EQ]": mapping.get("gds_sclsf_cd"),
        }
        return {key: value for key, value in params.items() if value not in {None, ""}}


def normalize_kamis_price_rows(
    payload: Any,
    item_code: str,
    default_date: date,
    source: str,
    product_cls: str,
    variant: dict[str, Any],
) -> list[PriceFeature]:
    features: list[PriceFeature] = []
    for row in _extract_kamis_rows(payload):
        if _looks_like_error(row):
            continue

        base_date = _kamis_row_date(row, default_date)
        region_code = first_present(row, "countycode", "region_code", "regionCode", "areaCd", "지역코드")
        region_name = first_present(row, "countyname", "지역명")
        value = parse_float(
            first_present(
                row,
                "price",
                "dpr1",
                "dpr2",
                "wpr1",
                "wpr2",
                "value",
                "당일",
                "가격",
                "소매가격",
                "도매가격",
            )
        )
        if value is None:
            continue

        raw = dict(row)
        raw["kamis_product_cls"] = product_cls
        raw["kamis_kindcode"] = variant.get("kindcode")
        raw["kamis_kind_name"] = variant.get("kind_name")

        features.append(
            PriceFeature(
                item_code=item_code,
                region_code=str(region_code or region_name) if (region_code or region_name) is not None else None,
                base_date=base_date,
                retail_price=value if product_cls == "01" else None,
                wholesale_price=value if product_cls == "02" else None,
                source=source,
                raw=raw,
            )
        )
    return features


def normalize_at_regional_price_rows(
    payload: Any,
    item_code: str,
    default_date: date,
    source: str,
) -> list[PriceFeature]:
    features: list[PriceFeature] = []
    for row in extract_rows(payload):
        base_date = parse_date(first_present(row, "exmn_ymd", "base_date", "date", "ymd"), default=default_date)
        region_code = first_present(row, "sgg_cd", "sgg_nm", "region_code", "regionCode")
        avg_price = parse_float(first_present(row, "exmn_dd_avg_prc", "exmn_dd_cnvs_avg_prc"))
        if avg_price is None:
            continue

        product_cls = str(first_present(row, "se_cd", "product_cls") or "")
        retail_price = avg_price if product_cls == "01" else None
        wholesale_price = avg_price if product_cls == "02" else None
        settlement_price = avg_price if retail_price is None and wholesale_price is None else None

        features.append(
            PriceFeature(
                item_code=item_code,
                region_code=str(region_code) if region_code is not None else None,
                base_date=base_date,
                retail_price=retail_price,
                wholesale_price=wholesale_price,
                settlement_price=settlement_price,
                source=source,
                raw=row,
            )
        )
    return features


def normalize_at_market_settlement_rows(
    payload: Any,
    item_code: str,
    default_date: date,
    source: str,
) -> list[PriceFeature]:
    features: list[PriceFeature] = []
    for row in extract_rows(payload):
        base_date = parse_date(first_present(row, "trd_clcln_ymd", "base_date", "date", "ymd"), default=default_date)
        region_code = first_present(row, "whsl_mrkt_cd", "whsl_mrkt_nm", "region_code", "regionCode")
        settlement_price = parse_float(first_present(row, "avgprc", "price", "settlement_price"))
        volume = parse_float(first_present(row, "unit_tot_qty", "tot_qty", "trd_qty", "qty", "volume", "unit_qty"))
        if settlement_price is None and volume is None:
            continue

        features.append(
            PriceFeature(
                item_code=item_code,
                region_code=str(region_code) if region_code is not None else None,
                base_date=base_date,
                settlement_price=settlement_price,
                volume=volume,
                source=source,
                raw=row,
            )
        )
    return features


def normalize_price_rows(
    payload: Any,
    item_code: str,
    default_date: date,
    source: str,
) -> list[PriceFeature]:
    features: list[PriceFeature] = []
    for row in extract_rows(payload):
        row_item_code = first_present(row, "item_code", "itemCode", "itemCd", "품목코드")
        if row_item_code and str(row_item_code) != item_code:
            continue

        base_date = parse_date(
            first_present(row, "base_date", "date", "regday", "ymd", "조사일자", "날짜"),
            default=default_date,
        )
        region_code = first_present(row, "region_code", "regionCode", "areaCd", "지역코드")
        retail_price = parse_float(first_present(row, "retail_price", "retailPrice", "dpr1", "소매가격"))
        wholesale_price = parse_float(first_present(row, "wholesale_price", "wholesalePrice", "wpr1", "도매가격"))
        settlement_price = parse_float(first_present(row, "settlement_price", "settlementPrice", "price", "정산가격"))
        volume = parse_float(first_present(row, "volume", "qty", "tradeVolume", "거래량"))

        features.append(
            PriceFeature(
                item_code=item_code,
                region_code=str(region_code) if region_code is not None else None,
                base_date=base_date,
                retail_price=retail_price,
                wholesale_price=wholesale_price,
                settlement_price=settlement_price,
                volume=volume,
                source=source,
                raw=row,
            )
        )
    return features


def _xml_to_payload(text: str) -> dict[str, Any]:
    root = ET.fromstring(text)
    rows = [_element_to_dict(item) for item in root.iter() if _local_name(item.tag) == "item"]
    if rows:
        return {"items": rows}
    return _element_to_dict(root)


def _extract_kamis_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("item")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
            if isinstance(items, dict):
                return [items]
    return extract_rows(payload)


def _kamis_row_date(row: dict[str, Any], default: date) -> date:
    year = first_present(row, "yyyy", "year")
    regday = first_present(row, "regday")
    if year and regday:
        return parse_date(f"{year}/{regday}", default=default)
    return parse_date(first_present(row, "base_date", "date", "ymd", "조사일자", "날짜"), default=default)


def _element_to_dict(element: ET.Element) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for child in list(element):
        key = _local_name(child.tag)
        grandchildren = list(child)
        if grandchildren:
            payload[key] = _element_to_dict(child)
        else:
            payload[key] = child.text.strip() if child.text else ""
    return payload


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _mapping_product_classes(mapping: dict[str, Any], default: list[str]) -> list[str]:
    product_classes = [str(item) for item in mapping.get("product_classes", []) if item]
    return product_classes or default


def _looks_like_error(row: dict[str, Any]) -> bool:
    code = str(first_present(row, "resultCode", "code", "errorCode") or "")
    message = str(first_present(row, "resultMsg", "message", "errorMsg") or "")
    return bool(code and code not in {"0", "00", "000"}) or "ERROR" in message.upper()


def _dedupe_price_features(features: list[PriceFeature]) -> list[PriceFeature]:
    deduped: list[PriceFeature] = []
    seen: set[tuple[Any, ...]] = set()
    for feature in features:
        key = (
            feature.item_code,
            feature.region_code,
            feature.base_date,
            feature.retail_price,
            feature.wholesale_price,
            feature.raw.get("kamis_product_cls") if isinstance(feature.raw, dict) else None,
            feature.raw.get("kamis_kindcode") if isinstance(feature.raw, dict) else None,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(feature)
    return deduped
