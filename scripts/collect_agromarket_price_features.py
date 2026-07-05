from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import dated_path, write_json


BASE_URL = "http://211.237.50.150:7080/openapi"
DEFAULT_ITEMS = ["cabbage", "radish", "onion", "green_onion", "garlic"]

ITEM_CODES = {
    "cabbage": {"category": "200", "item": "211", "name": "배추"},
    "radish": {"category": "200", "item": "231", "name": "무"},
    "onion": {"category": "200", "item": "245", "name": "양파"},
    "green_onion": {"category": "200", "item": "246", "name": "대파"},
    "garlic": {"category": "200", "item": "258", "name": "마늘"},
}

SETTLEMENT_CODES = {
    "cabbage": [{"large": "10", "mid": "01"}],
    "radish": [{"large": "11", "mid": "01"}],
    "onion": [{"large": "12", "mid": "01"}],
    "green_onion": [{"large": "12", "mid": "02"}],
    "garlic": [{"large": "12", "mid": "09"}],
}

GRIDS = {
    "wholesale": "Grid_20150406000000000217_1",
    "retail": "Grid_20141225000000000163_1",
    "settlement": "Grid_20240625000000000658_1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect AgroMarket price and settlement features.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--items", nargs="*", default=DEFAULT_ITEMS)
    parser.add_argument("--rows", type=int, default=200)
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
    for item_code in args.items:
        wholesale = collect_daily_price(api_key, "wholesale", item_code, start_date, target_date, args.rows)
        retail = collect_daily_price(api_key, "retail", item_code, start_date, target_date, args.rows)
        settlement = collect_settlement(api_key, item_code, start_date, target_date, args.rows)

        feature_sets = {
            "agromarket_wholesale_price": wholesale,
            "agromarket_retail_price": retail,
            "agromarket_settlement": settlement,
        }
        for source_name, features in feature_sets.items():
            out_path = dated_path("features", f"{source_name}_{item_code}", target_date)
            write_json(out_path, features)
            summaries.append({
                "source": source_name,
                "item_code": item_code,
                "feature_count": len(features),
                "feature_path": str(out_path),
            })

    payload = {
        "ok": any(item["feature_count"] for item in summaries),
        "target_date": target_date.isoformat(),
        "days_back": args.days_back,
        "items": args.items,
        "sources": summaries,
    }
    summary_path = dated_path("features", "agromarket_price_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps({**payload, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def collect_daily_price(api_key: str, kind: str, item_code: str, start_date: date, end_date: date, rows: int) -> list[dict[str, Any]]:
    item = ITEM_CODES.get(item_code)
    if not item:
        return []

    by_date: dict[date, list[float]] = {}
    raw_by_date: dict[str, list[dict[str, str]]] = {}
    for day in date_range(start_date, end_date):
        payload = request_grid(
            api_key,
            GRIDS[kind],
            {
                "EXAMIN_DE": f"{day:%Y%m%d}",
                "FRMPRD_CATGORY_CD": item["category"],
                "PRDLST_CD": item["item"],
            },
            rows,
        )
        values = []
        for row in payload:
            amount = parse_float(row.get("AMT"))
            if amount is None or amount <= 0:
                continue
            values.append(amount)
        if values:
            by_date[day] = values
            raw_by_date[day.isoformat()] = payload[:5]

    features = []
    for day, values in sorted(by_date.items()):
        avg_price = round(mean(values), 4)
        features.append({
            "item_code": item_code,
            "region_code": "agromarket_avg",
            "base_date": day.isoformat(),
            "retail_price": avg_price if kind == "retail" else None,
            "wholesale_price": avg_price if kind == "wholesale" else None,
            "settlement_price": None,
            "volume": None,
            "source": f"agromarket_{kind}_price",
            "raw": {
                "row_count": len(values),
                "sample_rows": raw_by_date.get(day.isoformat(), []),
            },
        })
    return features


def collect_settlement(api_key: str, item_code: str, start_date: date, end_date: date, rows: int) -> list[dict[str, Any]]:
    candidates = SETTLEMENT_CODES.get(item_code, [])
    by_date: dict[date, dict[str, float]] = {}
    raw_by_date: dict[str, list[dict[str, str]]] = {}
    for day in date_range(start_date, end_date):
        total_qty = 0.0
        total_amount = 0.0
        samples: list[dict[str, str]] = []
        for candidate in candidates:
            payload = request_grid(
                api_key,
                GRIDS["settlement"],
                {
                    "REGIST_DT": f"{day:%Y%m%d}",
                    "LARGE": candidate["large"],
                    "MID": candidate["mid"],
                },
                rows,
            )
            for row in payload:
                qty = parse_float(row.get("TOTQTY"))
                amount = parse_float(row.get("TOTAMT"))
                if qty is None or amount is None or qty <= 0 or amount <= 0:
                    continue
                total_qty += qty
                total_amount += amount
            samples.extend(payload[:3])
        if total_qty > 0 and total_amount > 0:
            by_date[day] = {"qty": total_qty, "amount": total_amount}
            raw_by_date[day.isoformat()] = samples[:6]

    features = []
    for day, totals in sorted(by_date.items()):
        avg_price = round(totals["amount"] / totals["qty"], 4)
        features.append({
            "item_code": item_code,
            "region_code": "agromarket_all_markets",
            "base_date": day.isoformat(),
            "retail_price": None,
            "wholesale_price": None,
            "settlement_price": avg_price,
            "volume": round(totals["qty"], 4),
            "source": "agromarket_settlement",
            "raw": {
                "total_qty": round(totals["qty"], 4),
                "total_amount": round(totals["amount"], 4),
                "sample_rows": raw_by_date.get(day.isoformat(), []),
            },
        })
    return features


def request_grid(api_key: str, grid_id: str, params: dict[str, Any], rows: int) -> list[dict[str, str]]:
    url = f"{BASE_URL}/{api_key}/xml/{grid_id}/1/{rows}"
    if params:
        url += "?" + urlencode(params)
    try:
        with urlopen(url, timeout=12) as response:
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


def child_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    return child.text if child is not None else None


if __name__ == "__main__":
    sys.exit(main())
