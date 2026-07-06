from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from zipfile import ZipFile
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.http import SimpleHttpClient
from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import encode, write_json


KAMIS_CODEBOOK_PATH = REPO_ROOT / "config" / "external_mappings" / "kamis_item_codes_download"
INDEX_HTML_PATH = REPO_ROOT / "index.html"
KAMIS_PRICE_BASE_URL = "https://www.kamis.or.kr/service/price/xml.do"
NAMESPACE = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NAMESPACE = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}


@dataclass(frozen=True)
class UiItem:
    item_code: str
    item_name: str


@dataclass(frozen=True)
class KamisCodeRow:
    category_code: str
    category_name: str
    item_code: str
    item_name: str
    kind_code: str
    kind_name: str
    wholesale_unit: str
    wholesale_unit_size: str
    retail_unit: str
    retail_unit_size: str
    wholesale_rank: str
    retail_rank: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit which UI candidate items have usable KAMIS price mappings.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--max-variants", type=int, default=8)
    parser.add_argument("--items", nargs="*", default=None, help="Optional UI item codes to audit.")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON path. Defaults to data/diagnostics/kamis_candidate_item_audit_<date>.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    target_date = date.fromisoformat(args.date)
    api_key = os.getenv("KAMIS_API_KEY")
    cert_id = os.getenv("KAMIS_CERT_ID") or os.getenv("KAMIS_API_ID") or "mkmap"
    if not api_key:
        print(json.dumps({"ok": False, "reason": "missing KAMIS_API_KEY"}, ensure_ascii=False, indent=2))
        return 2

    ui_items = parse_ui_items(INDEX_HTML_PATH)
    existing_items = {path.stem for path in (REPO_ROOT / "metadata" / "items").glob("*.json")}
    existing_kamis_mappings = load_existing_kamis_mappings()
    if args.items:
        wanted = set(args.items)
        ui_items = [item for item in ui_items if item.item_code in wanted]

    code_rows = parse_kamis_codebook(KAMIS_CODEBOOK_PATH)
    rows_by_name: dict[str, list[KamisCodeRow]] = {}
    for row in code_rows:
        rows_by_name.setdefault(row.item_name, []).append(row)

    http = SimpleHttpClient(timeout=20, verify_ssl=False)
    results = []
    for ui_item in ui_items:
        candidates = rows_by_name.get(ui_item.item_name, [])
        if not candidates:
            existing_mapping = existing_kamis_mappings.get(ui_item.item_code)
            if existing_mapping:
                results.append(
                    {
                        "item_code": ui_item.item_code,
                        "item_name": ui_item.item_name,
                        "status": "already_mapped",
                        "already_mapped": True,
                        "candidate_count": len(existing_mapping.get("variants", [])),
                        "tested_variants": [],
                        "best_variant": {
                            "category_code": existing_mapping.get("itemcategorycode"),
                            "itemcode": existing_mapping.get("itemcode"),
                            "kindcode": _primary_kindcode(existing_mapping),
                            "kind_name": _primary_kind_name(existing_mapping),
                            "source": "metadata/items",
                        },
                        "best_feature_count": None,
                        "notes": "No exact UI-name KAMIS codebook match, but metadata already contains a KAMIS mapping.",
                    }
                )
                continue
            results.append(
                {
                    "item_code": ui_item.item_code,
                    "item_name": ui_item.item_name,
                    "status": "no_mapping",
                    "already_mapped": ui_item.item_code in existing_items,
                    "candidate_count": 0,
                    "tested_variants": [],
                    "best_feature_count": 0,
                }
            )
            continue

        candidate_rows = prioritize_rows(candidates)[: args.max_variants]
        tested = []
        best_count = 0
        best_variant = None
        for row in candidate_rows:
            variant_result = audit_variant(http, api_key, cert_id, row, target_date, args.days_back)
            tested.append(variant_result)
            count = int(variant_result.get("feature_count") or 0)
            if count > best_count:
                best_count = count
                best_variant = variant_result

        if best_count >= max(3, min(args.days_back, 20) // 2):
            status = "ready"
        elif best_count > 0:
            status = "partial"
        else:
            status = "no_recent_price"

        results.append(
            {
                "item_code": ui_item.item_code,
                "item_name": ui_item.item_name,
                "status": status,
                "already_mapped": ui_item.item_code in existing_items,
                "candidate_count": len(candidates),
                "tested_variants": tested,
                "best_variant": best_variant,
                "best_feature_count": best_count,
            }
        )

    summary = summarize(results)
    payload = {
        "ok": True,
        "target_date": target_date.isoformat(),
        "days_back": args.days_back,
        "summary": summary,
        "items": results,
    }
    output = Path(args.output) if args.output else REPO_ROOT / "data" / "diagnostics" / f"kamis_candidate_item_audit_{target_date:%Y%m%d}.json"
    write_json(output, payload)
    print(json.dumps(encode(payload | {"output": str(output)}), ensure_ascii=False, indent=2))
    return 0


def parse_ui_items(path: Path) -> list[UiItem]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"const\s+ITEMS\s*=\s*\{(?P<body>.*?)\n\};", text, flags=re.S)
    if not match:
        raise ValueError("Could not find const ITEMS in index.html")
    body = match.group("body")
    items = []
    for item_code, item_name in re.findall(r"^\s*([A-Za-z0-9_]+)\s*:\s*\{name:\"([^\"]+)\"", body, flags=re.M):
        items.append(UiItem(item_code=item_code, item_name=item_name))
    return items


def load_existing_kamis_mappings() -> dict[str, dict[str, object]]:
    mappings: dict[str, dict[str, object]] = {}
    for path in sorted((REPO_ROOT / "metadata" / "items").glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        mapping = item.get("external_mappings", {}).get("kamis_price")
        if isinstance(mapping, dict) and mapping.get("itemcode"):
            mappings[str(item.get("item_code") or path.stem)] = mapping
    return mappings


def _primary_kindcode(mapping: dict[str, object]) -> str | None:
    variant = _primary_variant(mapping)
    return str(variant.get("kindcode")) if variant else None


def _primary_kind_name(mapping: dict[str, object]) -> str | None:
    variant = _primary_variant(mapping)
    return str(variant.get("kind_name")) if variant else None


def _primary_variant(mapping: dict[str, object]) -> dict[str, object] | None:
    variants = [variant for variant in mapping.get("variants", []) if isinstance(variant, dict)]
    if not variants:
        return None
    primary = [variant for variant in variants if variant.get("primary")]
    return primary[0] if primary else variants[0]


def parse_kamis_codebook(path: Path) -> list[KamisCodeRow]:
    rows = read_xlsx_sheet(path, "코드통합(부류+품목+품종코드)")
    if not rows:
        raise ValueError(f"No rows found in {path}")
    header = rows[0]
    index = {name: i for i, name in enumerate(header)}
    parsed = []
    for row in rows[1:]:
        if not any(row):
            continue
        parsed.append(
            KamisCodeRow(
                category_code=value(row, index, "품목 그룹코드"),
                category_name=value(row, index, "품목 그룹명"),
                item_code=value(row, index, "품목 코드"),
                item_name=value(row, index, "품목명"),
                kind_code=value(row, index, "품종코드"),
                kind_name=value(row, index, "품종명"),
                wholesale_unit=value(row, index, "도매출하단위"),
                wholesale_unit_size=value(row, index, "도매출하단위 크기"),
                retail_unit=value(row, index, "소매출하단위"),
                retail_unit_size=value(row, index, "소매출하단위 크기"),
                wholesale_rank=value(row, index, "도매 등급"),
                retail_rank=value(row, index, "소매 등급"),
            )
        )
    return parsed


def read_xlsx_sheet(path: Path, sheet_name: str) -> list[list[str]]:
    with ZipFile(path) as zf:
        shared = read_shared_strings(zf)
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        target = None
        for sheet in workbook.findall("a:sheets/a:sheet", NAMESPACE):
            if sheet.attrib.get("name") == sheet_name:
                rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
                target = relmap[rel_id]
                break
        if not target:
            raise ValueError(f"Sheet not found: {sheet_name}")
        sheet_path = "xl/" + target if not target.startswith("/") else target[1:]
        root = ET.fromstring(zf.read(sheet_path))
    return parse_sheet_rows(root, shared)


def read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall("a:si", NAMESPACE):
        values.append("".join(text.text or "" for text in item.findall(".//a:t", NAMESPACE)))
    return values


def parse_sheet_rows(root: ET.Element, shared: list[str]) -> list[list[str]]:
    parsed = []
    for row in root.findall("a:sheetData/a:row", NAMESPACE):
        cells: dict[int, str] = {}
        for cell in row.findall("a:c", NAMESPACE):
            ref = cell.attrib.get("r", "")
            col = column_index(ref)
            raw = cell.find("a:v", NAMESPACE)
            value_text = "" if raw is None else raw.text or ""
            if cell.attrib.get("t") == "s" and value_text:
                value_text = shared[int(value_text)]
            cells[col] = value_text.strip()
        if cells:
            max_col = max(cells)
            parsed.append([cells.get(i, "") for i in range(max_col + 1)])
    return parsed


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    result = 0
    for ch in letters:
        result = result * 26 + (ord(ch.upper()) - ord("A") + 1)
    return max(result - 1, 0)


def value(row: list[str], index: dict[str, int], key: str) -> str:
    position = index.get(key)
    if position is None or position >= len(row):
        return ""
    return row[position].strip()


def prioritize_rows(rows: list[KamisCodeRow]) -> list[KamisCodeRow]:
    def score(row: KamisCodeRow) -> tuple[int, int, str]:
        has_wholesale = 0 if row.wholesale_unit else 1
        generic_penalty = 1 if any(token in row.kind_name for token in ("기타", "수입", "냉동")) else 0
        return (has_wholesale, generic_penalty, row.kind_code)

    return sorted(rows, key=score)


def audit_variant(
    http: SimpleHttpClient,
    api_key: str,
    cert_id: str,
    row: KamisCodeRow,
    target_date: date,
    days_back: int,
) -> dict[str, object]:
    start_date = target_date - timedelta(days=max(days_back - 1, 0))
    counts_by_class = {}
    errors = []
    for product_cls in ("02", "01"):
        params = {
            "action": "periodProductList",
            "p_product_cls": product_cls,
            "p_cert_key": api_key,
            "p_cert_id": cert_id,
            "p_returntype": "json",
            "p_startday": start_date.isoformat(),
            "p_endday": target_date.isoformat(),
            "p_itemcategorycode": row.category_code,
            "p_itemcode": row.item_code,
            "p_kindcode": row.kind_code,
            "p_productrankcode": first_rank(row.wholesale_rank if product_cls == "02" else row.retail_rank) or "04",
        }
        try:
            payload = http.get(KAMIS_PRICE_BASE_URL, params=params).json()
            counts_by_class[product_cls] = count_price_rows(payload)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            counts_by_class[product_cls] = 0
            errors.append({"product_cls": product_cls, "error": type(exc).__name__})

    return {
        "category_code": row.category_code,
        "category_name": row.category_name,
        "itemcode": row.item_code,
        "kindcode": row.kind_code,
        "kind_name": row.kind_name,
        "wholesale_unit": unit_label(row.wholesale_unit, row.wholesale_unit_size),
        "retail_unit": unit_label(row.retail_unit, row.retail_unit_size),
        "feature_count": sum(counts_by_class.values()),
        "wholesale_count": counts_by_class.get("02", 0),
        "retail_count": counts_by_class.get("01", 0),
        "errors": errors,
    }


def first_rank(raw: str) -> str:
    return (raw.split(",")[0] if raw else "").strip()


def unit_label(unit: str, size: str) -> str:
    if not unit and not size:
        return ""
    return f"{size}{unit}" if size and unit else unit or size


def count_price_rows(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if not isinstance(data, dict):
        return 0
    items = data.get("item")
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return 0
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        county = str(item.get("countyname") or "")
        price = str(item.get("price") or "").strip()
        if county == "평균" and price and price != "-":
            count += 1
    return count


def summarize(results: list[dict[str, object]]) -> dict[str, object]:
    by_status: dict[str, int] = {}
    ready_unmapped = []
    partial_unmapped = []
    for result in results:
        status = str(result.get("status"))
        by_status[status] = by_status.get(status, 0) + 1
        if result.get("already_mapped"):
            continue
        if status == "ready":
            ready_unmapped.append(result.get("item_code"))
        elif status == "partial":
            partial_unmapped.append(result.get("item_code"))
    return {
        "total_items": len(results),
        "by_status": by_status,
        "ready_unmapped_items": ready_unmapped,
        "partial_unmapped_items": partial_unmapped,
    }


if __name__ == "__main__":
    raise SystemExit(main())
