from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import dated_path, write_json


BASE_URL = "http://211.237.50.150:7080/openapi"
GRID_ID = "Grid_20240625000000000654_1"
DEFAULT_ITEMS = ["cabbage", "radish", "onion", "green_onion", "garlic"]
DEFAULT_MARKETS = ["110001"]
VARIANT_GROUP_PATH = REPO_ROOT / "config" / "item_variant_groups.json"

AUCTION_CODES = {
    "cabbage": {"large": "10", "mid": "01"},
    "radish": {"large": "11", "mid": "01"},
    "onion": {"large": "12", "mid": "01"},
    "green_onion": {"large": "12", "mid": "02"},
    "garlic": {"large": "12", "mid": "09"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect AgroMarket realtime auction features.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--items", nargs="*", default=DEFAULT_ITEMS)
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    ensure_env_loaded()
    api_key = os.getenv("AGROMARKET_API_KEY", "")
    if not api_key:
        print(json.dumps({"ok": False, "reason": "missing_env", "missing": ["AGROMARKET_API_KEY"]}, ensure_ascii=False, indent=2))
        return 1

    args = parse_args()
    target_date = date.fromisoformat(args.date)
    start_date = target_date - timedelta(days=max(args.days_back - 1, 0))

    summaries = []
    variant_groups = load_variant_groups()
    for item_code in args.items:
        features = collect_item_auctions(
            api_key=api_key,
            item_code=item_code,
            start_date=start_date,
            end_date=target_date,
            markets=args.markets,
            rows=args.rows,
            max_pages=args.max_pages,
            variant_groups=variant_groups.get(item_code, {}),
        )
        out_path = dated_path("features", f"agromarket_auction_price_{item_code}", target_date)
        write_json(out_path, features)
        summaries.append({
            "source": "agromarket_auction_price",
            "item_code": item_code,
            "feature_count": len(features),
            "feature_path": str(out_path),
        })

    payload = {
        "ok": any(item["feature_count"] for item in summaries),
        "target_date": target_date.isoformat(),
        "days_back": args.days_back,
        "markets": args.markets,
        "items": args.items,
        "sources": summaries,
    }
    summary_path = dated_path("features", "agromarket_auction_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps({**payload, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def collect_item_auctions(
    api_key: str,
    item_code: str,
    start_date: date,
    end_date: date,
    markets: list[str],
    rows: int,
    max_pages: int,
    variant_groups: dict[str, list[str]],
) -> list[dict[str, Any]]:
    code = AUCTION_CODES.get(item_code)
    if not code:
        return []

    features = []
    for day in date_range(start_date, end_date):
        total_amount = 0.0
        total_qty = 0.0
        total_kg_amount = 0.0
        total_kg = 0.0
        row_count = 0
        normalized_row_count = 0
        sample_rows: list[dict[str, str]] = []
        markets_seen: set[str] = set()
        origins_seen: set[str] = set()
        variant_qty: dict[str, float] = {}
        for market in markets:
            payload = request_all_pages(
                api_key,
                {
                    "SALEDATE": f"{day:%Y%m%d}",
                    "WHSALCD": market,
                    "LARGE": code["large"],
                    "MID": code["mid"],
                },
                rows=rows,
                max_pages=max_pages,
            )
            for row in payload:
                cost = parse_float(row.get("COST"))
                qty = parse_float(row.get("QTY"))
                if cost is None or qty is None or cost <= 0 or qty <= 0:
                    continue
                total_amount += cost * qty
                total_qty += qty
                row_count += 1
                variant_group = classify_variant(row.get("SMALLNAME") or row.get("MIDNAME") or "", variant_groups)
                variant_qty[variant_group] = variant_qty.get(variant_group, 0.0) + qty
                kg_per_unit = parse_std_kg(row.get("STD"))
                if kg_per_unit:
                    price_per_kg = cost / kg_per_unit
                    if _plausible_price_per_kg(item_code, price_per_kg):
                        total_kg_amount += cost * qty
                        total_kg += kg_per_unit * qty
                        normalized_row_count += 1
                if row.get("WHSALNAME"):
                    markets_seen.add(str(row["WHSALNAME"]))
                if row.get("SANNAME"):
                    origins_seen.add(str(row["SANNAME"]))
            sample_rows.extend(payload[:3])

        if total_qty <= 0 or total_amount <= 0:
            continue
        dominant_variant, dominant_share = dominant_variant_share(variant_qty)
        normalized_price = round(total_kg_amount / total_kg, 4) if total_kg > 0 else None
        features.append({
            "item_code": item_code,
            "region_code": "agromarket_auction",
            "base_date": day.isoformat(),
            "retail_price": None,
            "wholesale_price": normalized_price,
            "settlement_price": None,
            "volume": round(total_qty, 4),
            "source": "agromarket_auction_price",
            "raw": {
                "market_codes": markets,
                "market_names": sorted(markets_seen),
                "origin_count": len(origins_seen),
                "row_count": row_count,
                "normalized_row_count": normalized_row_count,
                "total_kg": round(total_kg, 4),
                "dominant_variant_group": dominant_variant,
                "dominant_variant_share": round(dominant_share, 6),
                "variant_qty": {key: round(value, 4) for key, value in sorted(variant_qty.items())},
                "sample_rows": sample_rows[:6],
            },
        })
    return features


def request_all_pages(api_key: str, params: dict[str, Any], rows: int, max_pages: int) -> list[dict[str, str]]:
    all_rows: list[dict[str, str]] = []
    for page in range(max_pages):
        start = page * rows + 1
        end = (page + 1) * rows
        page_rows = request_grid(api_key, params, start, end)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        if len(page_rows) < rows:
            break
    return all_rows


def request_grid(api_key: str, params: dict[str, Any], start: int, end: int) -> list[dict[str, str]]:
    url = f"{BASE_URL}/{api_key}/xml/{GRID_ID}/{start}/{end}"
    url += "?" + urlencode(params)
    try:
        with urlopen(url, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
        root = ET.fromstring(text)
    except (URLError, TimeoutError, ET.ParseError):
        return []
    result = root.find("result")
    if result is not None and child_text(result, "code") not in {None, "INFO-000"}:
        return []
    return [{child.tag: child.text or "" for child in row} for row in root.findall("row")]


def date_range(start_date: date, end_date: date) -> list[date]:
    return [start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)]


def parse_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def load_variant_groups() -> dict[str, dict[str, list[str]]]:
    if not VARIANT_GROUP_PATH.exists():
        return {}
    payload = json.loads(VARIANT_GROUP_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    groups: dict[str, dict[str, list[str]]] = {}
    for item_code, item_payload in payload.items():
        if not isinstance(item_payload, dict):
            continue
        groups[str(item_code)] = {
            str(group): [str(token) for token in tokens if str(token)]
            for group, tokens in item_payload.items()
            if isinstance(tokens, list)
        }
    return groups


def classify_variant(name: str, groups: dict[str, list[str]]) -> str:
    text = str(name or "")
    for group, tokens in groups.items():
        if any(token and token in text for token in tokens):
            return group
    return "unknown"


def dominant_variant_share(variant_qty: dict[str, float]) -> tuple[str | None, float]:
    total = sum(value for value in variant_qty.values() if value > 0)
    if total <= 0:
        return None, 0.0
    group, qty = max(variant_qty.items(), key=lambda item: item[1])
    return group, qty / total


def parse_std_kg(value: Any) -> float | None:
    text = str(value or "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*kg", text, flags=re.IGNORECASE)
    if not match:
        return None
    kg = parse_float(match.group(1))
    if kg is None or kg <= 0:
        return None
    # Truck rows often encode total load size, not unit package size.
    if "트럭" in text or kg > 100:
        return None
    return kg


def _plausible_price_per_kg(item_code: str, price_per_kg: float) -> bool:
    ranges = {
        "cabbage": (100.0, 10000.0),
        "radish": (100.0, 10000.0),
        "onion": (100.0, 10000.0),
        "green_onion": (100.0, 20000.0),
        "garlic": (500.0, 30000.0),
    }
    low, high = ranges.get(item_code, (50.0, 50000.0))
    return low <= price_per_kg <= high


def child_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    return child.text if child is not None else None


if __name__ == "__main__":
    sys.exit(main())
