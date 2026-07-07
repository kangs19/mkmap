from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.registry import default_registry
from mkmap_meta.storage import dated_path, write_json


ITEM_TRADE_URL = "http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
CONFIG_PATH = REPO_ROOT / "config" / "customs_trade_hs_candidates.json"

CONFIDENCE_SCORE = {"high": 1.0, "medium": 0.65, "low": 0.25}
TRAINABLE_READINESS = {
    "ready_for_import_pressure_feature",
    "usable_after_hs_name_review",
    "no_recent_import_rows",
}

STATKOR_ALLOWLIST = {
    "cabbage": {"배추"},
    "radish": set(),
    "green_onion": {"대파"},
    "pepper": {"건조한 것(부수지도 잘게 부수지도 않은 것)", "부수거나 잘게 부순 것"},
    "fresh_pepper": set(),
    "cucumber": {"오이류(신선한 것이나 냉장한 것으로 한정한다)"},
    "lettuce": {"결구(結球) 상추"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect monthly customs import/export features for crop price models.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Cache date, YYYY-MM-DD")
    parser.add_argument("--start-month", default="2024-01", help="YYYY-MM")
    parser.add_argument("--end-month", default=None, help="YYYY-MM. Defaults to previous calendar month.")
    parser.add_argument("--items", nargs="*", default=None)
    parser.add_argument("--sleep", type=float, default=0.08)
    return parser.parse_args()


def main() -> int:
    ensure_env_loaded()
    if not os.getenv("DATA_GO_KR_API_KEY"):
        print(json.dumps({"ok": False, "reason": "missing_env", "missing": ["DATA_GO_KR_API_KEY"]}, ensure_ascii=False, indent=2))
        return 1

    args = parse_args()
    target_date = date.fromisoformat(args.date)
    start_month = _month_to_yymm(args.start_month)
    end_month = _month_to_yymm(args.end_month) if args.end_month else _previous_month_yymm(target_date)
    windows = _month_windows(start_month, end_month)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    registry = default_registry()
    item_codes = args.items or sorted(registry.all_items())

    summaries: list[dict[str, Any]] = []
    for item_code in item_codes:
        item_config = config.get("items", {}).get(item_code)
        if not item_config:
            continue
        readiness = item_config.get("feature_readiness")
        if readiness not in TRAINABLE_READINESS:
            summaries.append({"item_code": item_code, "ok": True, "skipped": True, "reason": readiness})
            continue

        rows: list[dict[str, str]] = []
        errors: list[str] = []
        for hs_prefix in item_config.get("hs_prefixes", []):
            for start, end in windows:
                try:
                    rows.extend(_request_rows(start, end, hs_prefix))
                except Exception as exc:
                    errors.append(f"{hs_prefix}:{start}-{end}:{exc}")
                time.sleep(args.sleep)

        features = _normalize_item_rows(item_code, item_config, rows)
        out_path = dated_path("features", f"customs_trade_{item_code}", target_date)
        write_json(out_path, features)
        summaries.append(
            {
                "item_code": item_code,
                "ok": not errors,
                "errors": errors[:5],
                "raw_row_count": len(rows),
                "feature_count": len(features),
                "date_min": min((row["base_date"] for row in features), default=None),
                "date_max": max((row["base_date"] for row in features), default=None),
                "feature_path": str(out_path),
                "feature_readiness": readiness,
            }
        )

    payload = {
        "ok": any(row.get("feature_count", 0) > 0 for row in summaries),
        "target_date": target_date.isoformat(),
        "start_month": _yymm_to_month(start_month),
        "end_month": _yymm_to_month(end_month),
        "source": ITEM_TRADE_URL,
        "items": summaries,
    }
    summary_path = dated_path("features", "customs_trade_collection_summary", target_date)
    write_json(summary_path, payload)
    print(json.dumps({**payload, "summary_path": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _request_rows(start_yymm: str, end_yymm: str, hs_prefix: str) -> list[dict[str, str]]:
    key = os.getenv("DATA_GO_KR_API_KEY", "")
    query = urlencode({"serviceKey": key, "strtYymm": start_yymm, "endYymm": end_yymm, "hsSgn": hs_prefix})
    with urlopen(f"{ITEM_TRADE_URL}?{query}", timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(text)
    code = root.findtext(".//resultCode")
    if code and code != "00":
        raise RuntimeError(root.findtext(".//resultMsg") or f"resultCode={code}")
    result = []
    for item in root.findall(".//item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        if row.get("year") == "총계":
            continue
        result.append(row)
    return result


def _normalize_item_rows(item_code: str, item_config: dict[str, Any], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    allowlist = STATKOR_ALLOWLIST.get(item_code)
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "import_weight_kg": 0.0,
            "import_value_usd": 0.0,
            "export_weight_kg": 0.0,
            "export_value_usd": 0.0,
            "hs_codes": set(),
            "stat_names": set(),
        }
    )
    for row in rows:
        stat_name = row.get("statKor", "")
        if allowlist is not None and stat_name not in allowlist:
            continue
        month = _api_year_to_month(row.get("year", ""))
        if not month:
            continue
        bucket = grouped[month]
        bucket["import_weight_kg"] += _float(row.get("impWgt"))
        bucket["import_value_usd"] += _float(row.get("impDlr"))
        bucket["export_weight_kg"] += _float(row.get("expWgt"))
        bucket["export_value_usd"] += _float(row.get("expDlr"))
        if row.get("hsCode"):
            bucket["hs_codes"].add(row["hsCode"])
        if stat_name:
            bucket["stat_names"].add(stat_name)

    confidence = item_config.get("mapping_confidence", "low")
    readiness = item_config.get("feature_readiness", "")
    features = []
    for month, values in sorted(grouped.items()):
        import_weight = values["import_weight_kg"]
        import_value = values["import_value_usd"]
        export_weight = values["export_weight_kg"]
        features.append(
            {
                "item_code": item_code,
                "base_date": f"{month}-01",
                "source": "customs_item_trade",
                "feature_readiness": readiness,
                "mapping_confidence": confidence,
                "mapping_confidence_score": CONFIDENCE_SCORE.get(confidence, 0.0),
                "trade_available": 1 if import_weight > 0 or export_weight > 0 else 0,
                "import_weight_kg": round(import_weight, 6),
                "import_value_usd": round(import_value, 6),
                "import_unit_value_usd_per_kg": round(import_value / import_weight, 6) if import_weight > 0 else 0.0,
                "export_weight_kg": round(export_weight, 6),
                "export_value_usd": round(values["export_value_usd"], 6),
                "net_import_weight_kg": round(import_weight - export_weight, 6),
                "hs_codes": sorted(values["hs_codes"]),
                "stat_names": sorted(values["stat_names"]),
            }
        )
    return features


def _month_windows(start_yymm: str, end_yymm: str) -> list[tuple[str, str]]:
    start_year, start_month = int(start_yymm[:4]), int(start_yymm[4:6])
    end_year, end_month = int(end_yymm[:4]), int(end_yymm[4:6])
    windows = []
    cur_year, cur_month = start_year, start_month
    while (cur_year, cur_month) <= (end_year, end_month):
        win_start_year, win_start_month = cur_year, cur_month
        win_end_year, win_end_month = _add_months(cur_year, cur_month, 11)
        if (win_end_year, win_end_month) > (end_year, end_month):
            win_end_year, win_end_month = end_year, end_month
        windows.append((f"{win_start_year:04d}{win_start_month:02d}", f"{win_end_year:04d}{win_end_month:02d}"))
        cur_year, cur_month = _add_months(win_end_year, win_end_month, 1)
    return windows


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def _month_to_yymm(value: str) -> str:
    value = value.strip()
    if len(value) == 6 and value.isdigit():
        return value
    year, month = value.split("-", 1)
    return f"{int(year):04d}{int(month):02d}"


def _yymm_to_month(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}"


def _previous_month_yymm(target_date: date) -> str:
    year, month = target_date.year, target_date.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}{month:02d}"


def _api_year_to_month(value: str) -> str | None:
    value = value.strip().replace(".", "-")
    if len(value) >= 7:
        try:
            year = int(value[:4])
            month = int(value[5:7])
            return f"{year:04d}-{month:02d}"
        except ValueError:
            return None
    return None


def _float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    sys.exit(main())
