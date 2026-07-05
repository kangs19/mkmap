from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded


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
    "cabbage": [
        {"large": "10", "mid": "01", "label": "엽경채류/배추"},
    ],
    "radish": [
        {"large": "11", "mid": "01", "label": "근채류/무"},
    ],
    "onion": [
        {"large": "12", "mid": "01", "label": "조미채소류/양파"},
    ],
    "green_onion": [
        {"large": "12", "mid": "02", "label": "조미채소류/대파"},
    ],
    "garlic": [
        {"large": "12", "mid": "09", "label": "조미채소류/마늘"},
    ],
}


@dataclass(frozen=True)
class Grid:
    code: str
    grid_id: str
    role: str
    priority: str
    required_params: list[str]
    notes: str


GRIDS = [
    Grid(
        code="wholesale_price",
        grid_id="Grid_20150406000000000217_1",
        role="price_level",
        priority="P0",
        required_params=["EXAMIN_DE"],
        notes="일별 도매가격. KAMIS 가격과 교차검증 및 직접 모델 feature로 사용.",
    ),
    Grid(
        code="retail_price",
        grid_id="Grid_20141225000000000163_1",
        role="price_level",
        priority="P0",
        required_params=["EXAMIN_DE"],
        notes="일별 소매가격. 소매-도매 spread와 소비자 가격 전이 feature.",
    ),
    Grid(
        code="settlement_volume_amount",
        grid_id="Grid_20240625000000000658_1",
        role="market_pressure",
        priority="P0",
        required_params=["REGIST_DT"],
        notes="도매시장별 품목별 총물량/총금액. 평균 정산가, 물량 압력, 시장 편중 feature.",
    ),
    Grid(
        code="realtime_auction",
        grid_id="Grid_20240625000000000654_1",
        role="market_pressure",
        priority="P1",
        required_params=["SALEDATE", "WHSALCD"],
        notes="실시간 경매정보. 선행성은 높지만 시장/품목 필수 코드 매핑 필요.",
    ),
    Grid(
        code="rain_reservoir",
        grid_id="Grid_20250220000000000669_1",
        role="weather_supply_risk",
        priority="P1",
        required_params=[],
        notes="지역별 누적 강수량과 농업용수 저수율. 가뭄/과우 위험 feature.",
    ),
    Grid(
        code="weather_alert_insurance",
        grid_id="Grid_20250220000000000671_1",
        role="disaster_risk",
        priority="P1",
        required_params=[],
        notes="월별 법정동 기상특보 횟수와 농작물재해보험 가입 규모.",
    ),
    Grid(
        code="eco_price",
        grid_id="Grid_20141225000000000160_1",
        role="segment_price",
        priority="P2",
        required_params=["EXAMIN_DE"],
        notes="친환경 가격. 메인 예측보다 세그먼트 프리미엄 feature 후보.",
    ),
    Grid(
        code="rural_village",
        grid_id="Grid_20151210000000000334_1",
        role="static_region_context",
        priority="P3",
        required_params=["BJDNGCD"],
        notes="농촌 마을 현황. 가격 단기예측 직접 기여도는 낮음.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit newly approved AgroMarket data availability for MK-MAP price prediction.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--items", nargs="+", default=DEFAULT_ITEMS)
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    ensure_env_loaded()
    api_key = os.getenv("AGROMARKET_API_KEY", "")
    if not api_key:
        print(json.dumps({"ok": False, "reason": "missing_env", "missing": ["AGROMARKET_API_KEY"]}, ensure_ascii=False, indent=2))
        return 1

    args = parse_args()
    target_date = date.fromisoformat(args.date)
    report = {
        "ok": True,
        "date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "items": args.items,
        "summary": {},
        "checks": [],
        "recommendations": [],
    }

    for grid in GRIDS:
        if grid.code in {"wholesale_price", "retail_price", "eco_price"}:
            report["checks"].extend(audit_daily_price_grid(api_key, grid, target_date, args.lookback_days, args.items, args.rows))
        elif grid.code == "settlement_volume_amount":
            report["checks"].extend(audit_settlement_grid(api_key, grid, target_date, args.lookback_days, args.items, args.rows))
        elif grid.code == "realtime_auction":
            report["checks"].append(audit_required_only(api_key, grid, target_date, args.rows))
        else:
            report["checks"].append(audit_unfiltered_grid(api_key, grid, args.rows))

    report["summary"] = summarize(report["checks"])
    report["recommendations"] = recommendations(report["checks"])

    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    return 0


def audit_daily_price_grid(
    api_key: str,
    grid: Grid,
    target_date: date,
    lookback_days: int,
    items: list[str],
    rows: int,
) -> list[dict[str, Any]]:
    checks = []
    for item_code in items:
        item = ITEM_CODES.get(item_code)
        if not item:
            continue
        for day in _sample_dates(target_date, lookback_days):
            params = {
                "EXAMIN_DE": f"{day:%Y%m%d}",
                "FRMPRD_CATGORY_CD": item["category"],
                "PRDLST_CD": item["item"],
            }
            payload = request_grid(api_key, grid.grid_id, params, rows)
            checks.append(make_check(grid, item_code, day, params, payload))
            if payload["row_count"] > 0:
                break
    return checks


def audit_settlement_grid(
    api_key: str,
    grid: Grid,
    target_date: date,
    lookback_days: int,
    items: list[str],
    rows: int,
) -> list[dict[str, Any]]:
    checks = []
    for item_code in items:
        candidates = SETTLEMENT_CODES.get(item_code, [])
        if not candidates:
            continue
        for candidate in candidates:
            for day in _sample_dates(target_date, lookback_days):
                params = {
                    "REGIST_DT": f"{day:%Y%m%d}",
                    "LARGE": candidate["large"],
                    "MID": candidate["mid"],
                }
                payload = request_grid(api_key, grid.grid_id, params, rows)
                check = make_check(grid, item_code, day, params, payload)
                check["mapping_candidate"] = candidate
                checks.append(check)
                if payload["row_count"] > 0:
                    break
    return checks


def audit_unfiltered_grid(api_key: str, grid: Grid, rows: int) -> dict[str, Any]:
    payload = request_grid(api_key, grid.grid_id, {}, rows)
    return make_check(grid, None, None, {}, payload)


def audit_required_only(api_key: str, grid: Grid, target_date: date, rows: int) -> dict[str, Any]:
    # Known required fields are documented, but market code must be discovered before this is useful.
    params = {"SALEDATE": f"{target_date:%Y%m%d}", "WHSALCD": "110001"}
    payload = request_grid(api_key, grid.grid_id, params, rows)
    return make_check(grid, None, target_date, params, payload)


def request_grid(api_key: str, grid_id: str, params: dict[str, Any], rows: int) -> dict[str, Any]:
    url = f"{BASE_URL}/{api_key}/xml/{grid_id}/1/{rows}"
    if params:
        url += "?" + urlencode(params)
    try:
        with urlopen(url, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "status": "request_error", "error": str(exc), "row_count": 0, "fields": []}

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {"ok": False, "status": "invalid_xml", "error": str(exc), "row_count": 0, "fields": [], "preview": text[:300]}

    result = root.find("result")
    code = _child_text(result, "code") if result is not None else None
    message = _child_text(result, "message") if result is not None else None
    rows_payload = [_row_to_dict(row) for row in root.findall("row")]
    total_count = _child_text(root, "totalCnt")
    fields = sorted(rows_payload[0].keys()) if rows_payload else []
    return {
        "ok": code == "INFO-000",
        "status": code or "unknown",
        "message": message,
        "total_count": int(total_count) if total_count and total_count.isdigit() else None,
        "row_count": len(rows_payload),
        "fields": fields,
        "sample": rows_payload[:2],
    }


def make_check(grid: Grid, item_code: str | None, day: date | None, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "grid": grid.code,
        "grid_id": grid.grid_id,
        "role": grid.role,
        "priority": grid.priority,
        "item_code": item_code,
        "date": day.isoformat() if day else None,
        "params": params,
        "required_params": grid.required_params,
        "notes": grid.notes,
        "ok": payload.get("ok", False) and payload.get("row_count", 0) > 0,
        "payload": payload,
    }


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    by_grid: dict[str, dict[str, Any]] = {}
    for check in checks:
        grid = check["grid"]
        bucket = by_grid.setdefault(grid, {"checks": 0, "ok_checks": 0, "items_with_rows": set(), "max_total_count": 0})
        bucket["checks"] += 1
        if check["ok"]:
            bucket["ok_checks"] += 1
            if check.get("item_code"):
                bucket["items_with_rows"].add(check["item_code"])
        total_count = check.get("payload", {}).get("total_count") or 0
        bucket["max_total_count"] = max(bucket["max_total_count"], total_count)

    return {
        grid: {
            **{key: value for key, value in bucket.items() if key != "items_with_rows"},
            "items_with_rows": sorted(bucket["items_with_rows"]),
        }
        for grid, bucket in by_grid.items()
    }


def recommendations(checks: list[dict[str, Any]]) -> list[dict[str, str]]:
    summary = summarize(checks)
    ordered = []
    for grid in ["wholesale_price", "retail_price", "settlement_volume_amount", "realtime_auction", "rain_reservoir", "weather_alert_insurance", "eco_price", "rural_village"]:
        info = summary.get(grid, {})
        ok_checks = info.get("ok_checks", 0)
        if grid in {"wholesale_price", "retail_price"} and ok_checks:
            action = "P0: add as direct price history/cross-check feature."
        elif grid == "settlement_volume_amount" and ok_checks:
            action = "P0: add volume/amount market pressure feature after confirming item code mapping."
        elif grid == "realtime_auction":
            action = "P1: discover required WHSALCD/item parameters before feature integration."
        elif grid in {"rain_reservoir", "weather_alert_insurance"} and ok_checks:
            action = "P1: add regional supply-risk feature and join by region/date/month."
        elif grid == "eco_price" and ok_checks:
            action = "P2: use for eco premium/segment signal, not core MVP."
        else:
            action = "Hold: mapping or required parameters need more discovery."
        ordered.append({"grid": grid, "action": action})
    return ordered


def _sample_dates(target_date: date, lookback_days: int) -> list[date]:
    return [target_date - timedelta(days=offset) for offset in range(0, lookback_days + 1)]


def _row_to_dict(element: ET.Element) -> dict[str, str]:
    return {child.tag: child.text or "" for child in element}


def _child_text(element: ET.Element | None, tag: str) -> str | None:
    if element is None:
        return None
    child = element.find(tag)
    return child.text if child is not None else None


if __name__ == "__main__":
    sys.exit(main())
