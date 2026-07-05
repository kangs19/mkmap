from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import dated_path, write_json


BASE_URL = "http://211.237.50.150:7080/openapi"
GRIDS = {
    "rain_reservoir": "Grid_20250220000000000669_1",
    "weather_alert_insurance": "Grid_20250220000000000671_1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect AgroMarket monthly supply-risk context features.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Cache date, YYYY-MM-DD")
    parser.add_argument("--start-month", required=True, help="YYYY-MM")
    parser.add_argument("--end-month", required=True, help="YYYY-MM")
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    ensure_env_loaded()
    api_key = os.getenv("AGROMARKET_API_KEY", "")
    if not api_key:
        print(json.dumps({"ok": False, "reason": "missing_env", "missing": ["AGROMARKET_API_KEY"]}, ensure_ascii=False, indent=2))
        return 1

    args = parse_args()
    target_date = date.fromisoformat(args.date)
    start_month = _normalize_month(args.start_month)
    end_month = _normalize_month(args.end_month)
    summaries = []

    for source_name, grid_id in GRIDS.items():
        rows = request_all_pages(api_key, grid_id, rows=args.rows, max_pages=args.max_pages)
        filtered = [row for row in rows if start_month <= _normalize_month(str(row.get("TOT_YM") or "")) <= end_month]
        features = normalize_rows(source_name, filtered)
        out_path = dated_path("features", source_name, target_date)
        write_json(out_path, features)
        summaries.append(
            {
                "source": source_name,
                "raw_row_count": len(rows),
                "feature_count": len(features),
                "date_min": min((row["base_date"] for row in features), default=None),
                "date_max": max((row["base_date"] for row in features), default=None),
                "feature_path": str(out_path),
            }
        )

    payload = {
        "ok": any(row["feature_count"] for row in summaries),
        "target_date": target_date.isoformat(),
        "start_month": start_month,
        "end_month": end_month,
        "sources": summaries,
    }
    summary_path = dated_path("features", "agromarket_supply_context_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps({**payload, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def request_all_pages(api_key: str, grid_id: str, rows: int, max_pages: int) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    for page in range(max_pages):
        start = page * rows + 1
        end = (page + 1) * rows
        payload = request_grid(api_key, grid_id, start, end)
        if not payload:
            break
        collected.extend(payload)
        if len(payload) < rows:
            break
    return collected


def request_grid(api_key: str, grid_id: str, start: int, end: int) -> list[dict[str, str]]:
    url = f"{BASE_URL}/{api_key}/xml/{grid_id}/{start}/{end}"
    try:
        with urlopen(url, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
        root = ET.fromstring(text)
    except (URLError, TimeoutError, ET.ParseError):
        return []
    result = root.find("result")
    if result is not None and _child_text(result, "code") not in {None, "INFO-000"}:
        return []
    return [{child.tag: child.text or "" for child in row} for row in root.findall("row")]


def normalize_rows(source_name: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    features = []
    for row in rows:
        month = _normalize_month(str(row.get("TOT_YM") or ""))
        if not month:
            continue
        if source_name == "rain_reservoir":
            rainfall = _float(row.get("RNFL_MSRVL"))
            reservoir = _float(row.get("STWTR_RTO_MSRVL"))
            severity = _rain_reservoir_score(rainfall, reservoir)
            region_code = row.get("AREA_SPR_CD") or ""
            title = "monthly rain and reservoir risk"
        else:
            severity = _alert_insurance_score(row)
            region_code = row.get("BJDNGCD") or ""
            title = "monthly weather alert and crop-insurance exposure"
        features.append(
            {
                "region_code": region_code,
                "base_date": f"{month}-01",
                "event_type": source_name,
                "level": _level(severity),
                "title": title,
                "description": f"{source_name} {month}",
                "severity_score": round(severity, 6),
                "source": source_name,
                "raw": row,
            }
        )
    return features


def _rain_reservoir_score(rainfall: float | None, reservoir: float | None) -> float:
    rain_score = min(max((rainfall or 0.0) / 500.0, 0.0), 1.0)
    drought_score = 0.0
    if reservoir is not None:
        drought_score = min(max((60.0 - reservoir) / 60.0, 0.0), 1.0)
    return max(rain_score, drought_score)


def _alert_insurance_score(row: dict[str, str]) -> float:
    alert_fields = [
        "ARD_SPCRPT_CNT",
        "CLDWAVE_SPCRPT_CNT",
        "HTWAVE_SPCRPT_CNT",
        "HVSNW_SPCRPT_CNT",
        "HVYRN_SPCRPT_CNT",
        "STRWND_SPCRPT_CNT",
        "TPHN_SPCRPT_CNT",
        "TSNM_SPCRPT_CNT",
        "YLWDST_SPCRPT_CNT",
    ]
    weighted = 0.0
    for field in alert_fields:
        value = _float(row.get(field)) or 0.0
        weight = 1.5 if field in {"HTWAVE_SPCRPT_CNT", "CLDWAVE_SPCRPT_CNT", "HVYRN_SPCRPT_CNT", "TPHN_SPCRPT_CNT"} else 1.0
        weighted += value * weight
    insured_area = _float(row.get("JOIN_SFC")) or 0.0
    exposure = min(insured_area / 10_000_000.0, 1.0)
    return min((weighted / 20.0) * (0.5 + exposure * 0.5), 1.0)


def _level(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _normalize_month(value: str) -> str:
    raw = "".join(ch for ch in value if ch.isdigit())
    if len(raw) < 6:
        return ""
    return f"{raw[:4]}-{raw[4:6]}"


def _float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _child_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    return child.text if child is not None else None


if __name__ == "__main__":
    sys.exit(main())
