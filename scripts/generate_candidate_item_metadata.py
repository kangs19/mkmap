from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ITEMS_DIR = REPO_ROOT / "metadata" / "items"
INDEX_HTML_PATH = REPO_ROOT / "index.html"


PROVINCE_CODES = {
    "강원도": "42",
    "경기도": "41",
    "경상남도": "48",
    "경상북도": "47",
    "전라남도": "46",
    "전라북도": "45",
    "충청남도": "44",
    "충청북도": "43",
    "제주도": "50",
}


ITEM_PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "potato": {
        "storage_type": "semi_storage",
        "cultivation_type": ["open_field", "spring", "summer", "stored"],
        "growth_calendar": {"spring": [3, 4, 5], "highland": [5, 6, 7]},
        "harvest_calendar": {"main": [6, 7, 8], "storage": [9, 10]},
        "weather": {"heat": 0.55, "cold": 0.45, "heavy_rain": 0.75, "drought": 0.55, "humidity": 0.65},
        "critical_windows": [{"name": "tuber_growth", "months": [5, 6, 7], "risk_factors": ["heavy_rain", "drought", "humidity"]}],
    },
    "sweet_potato": {
        "storage_type": "storage",
        "cultivation_type": ["open_field", "stored"],
        "growth_calendar": {"main": [5, 6, 7, 8]},
        "harvest_calendar": {"main": [9, 10, 11]},
        "weather": {"heat": 0.45, "cold": 0.35, "heavy_rain": 0.65, "drought": 0.55, "humidity": 0.55},
        "critical_windows": [{"name": "root_growth", "months": [7, 8, 9], "risk_factors": ["heavy_rain", "drought"]}],
    },
    "pepper": {
        "storage_type": "processed_or_storage",
        "cultivation_type": ["open_field", "stored"],
        "growth_calendar": {"main": [5, 6, 7, 8]},
        "harvest_calendar": {"drying": [8, 9, 10]},
        "weather": {"heat": 0.7, "cold": 0.35, "heavy_rain": 0.85, "drought": 0.55, "humidity": 0.85, "sunshine": 0.7},
        "critical_windows": [{"name": "drying_quality", "months": [8, 9, 10], "risk_factors": ["heavy_rain", "humidity", "sunshine"]}],
    },
    "fresh_pepper": {
        "storage_type": "fresh",
        "cultivation_type": ["open_field", "facility", "summer"],
        "growth_calendar": {"main": [4, 5, 6, 7, 8]},
        "harvest_calendar": {"main": [6, 7, 8, 9, 10]},
        "weather": {"heat": 0.75, "cold": 0.45, "heavy_rain": 0.8, "drought": 0.55, "humidity": 0.75},
        "critical_windows": [{"name": "summer_fruiting", "months": [7, 8, 9], "risk_factors": ["heat", "heavy_rain", "humidity"]}],
    },
    "tomato": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "open_field"],
        "growth_calendar": {"facility": [1, 2, 3, 4, 5, 6, 10, 11, 12]},
        "harvest_calendar": {"facility": [1, 2, 3, 4, 5, 6, 11, 12]},
        "weather": {"heat": 0.8, "cold": 0.55, "heavy_rain": 0.45, "drought": 0.35, "humidity": 0.75, "sunshine": 0.65},
        "critical_windows": [{"name": "facility_fruiting", "months": [1, 2, 3, 6, 7, 8, 12], "risk_factors": ["heat", "cold", "humidity", "sunshine"]}],
    },
    "cucumber": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "open_field", "summer"],
        "growth_calendar": {"facility": [1, 2, 3, 4, 5, 9, 10, 11, 12], "summer": [5, 6, 7, 8]},
        "harvest_calendar": {"main": [3, 4, 5, 6, 7, 8, 9, 10]},
        "weather": {"heat": 0.8, "cold": 0.5, "heavy_rain": 0.7, "drought": 0.45, "humidity": 0.85},
        "critical_windows": [{"name": "fruit_set", "months": [6, 7, 8], "risk_factors": ["heat", "heavy_rain", "humidity"]}],
    },
    "carrot": {
        "storage_type": "semi_storage",
        "cultivation_type": ["open_field", "winter", "stored"],
        "growth_calendar": {"main": [8, 9, 10, 11]},
        "harvest_calendar": {"main": [12, 1, 2, 3]},
        "weather": {"heat": 0.45, "cold": 0.55, "heavy_rain": 0.7, "drought": 0.5, "wind": 0.45},
        "critical_windows": [{"name": "winter_root", "months": [11, 12, 1, 2], "risk_factors": ["cold", "heavy_rain", "wind"]}],
    },
    "spinach": {
        "storage_type": "fresh",
        "cultivation_type": ["open_field", "facility", "winter"],
        "growth_calendar": {"cool_season": [9, 10, 11, 12, 1, 2, 3]},
        "harvest_calendar": {"main": [10, 11, 12, 1, 2, 3]},
        "weather": {"heat": 0.8, "cold": 0.45, "heavy_rain": 0.65, "drought": 0.45, "humidity": 0.7},
        "critical_windows": [{"name": "cool_leaf_growth", "months": [11, 12, 1, 2], "risk_factors": ["cold", "heavy_rain", "humidity"]}],
    },
    "lettuce": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "open_field"],
        "growth_calendar": {"year_round": [1, 2, 3, 4, 5, 6, 9, 10, 11, 12]},
        "harvest_calendar": {"year_round": [1, 2, 3, 4, 5, 6, 9, 10, 11, 12]},
        "weather": {"heat": 0.85, "cold": 0.45, "heavy_rain": 0.55, "drought": 0.35, "humidity": 0.8},
        "critical_windows": [{"name": "leaf_quality", "months": [6, 7, 8, 12, 1], "risk_factors": ["heat", "cold", "humidity"]}],
    },
    "perilla": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "open_field"],
        "growth_calendar": {"main": [3, 4, 5, 6, 7, 8, 9]},
        "harvest_calendar": {"main": [5, 6, 7, 8, 9, 10]},
        "weather": {"heat": 0.6, "cold": 0.5, "heavy_rain": 0.55, "drought": 0.4, "humidity": 0.75, "sunshine": 0.55},
        "critical_windows": [{"name": "leaf_harvest", "months": [6, 7, 8, 9], "risk_factors": ["humidity", "heavy_rain", "sunshine"]}],
    },
    "watermelon": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "open_field", "summer"],
        "growth_calendar": {"main": [3, 4, 5, 6]},
        "harvest_calendar": {"main": [6, 7, 8]},
        "weather": {"heat": 0.65, "cold": 0.5, "heavy_rain": 0.8, "drought": 0.45, "humidity": 0.75, "sunshine": 0.75},
        "critical_windows": [{"name": "fruit_enlargement", "months": [5, 6, 7], "risk_factors": ["heavy_rain", "humidity", "sunshine"]}],
    },
    "chamoe": {
        "storage_type": "fresh",
        "cultivation_type": ["facility", "summer"],
        "growth_calendar": {"main": [2, 3, 4, 5]},
        "harvest_calendar": {"main": [4, 5, 6, 7]},
        "weather": {"heat": 0.65, "cold": 0.55, "heavy_rain": 0.65, "drought": 0.35, "humidity": 0.75, "sunshine": 0.7},
        "critical_windows": [{"name": "facility_melon_quality", "months": [4, 5, 6], "risk_factors": ["humidity", "sunshine", "heavy_rain"]}],
    },
    "sesame": {
        "storage_type": "processed_or_storage",
        "cultivation_type": ["open_field", "stored"],
        "growth_calendar": {"main": [5, 6, 7]},
        "harvest_calendar": {"main": [8, 9, 10]},
        "weather": {"heat": 0.55, "cold": 0.35, "heavy_rain": 0.85, "drought": 0.55, "humidity": 0.8},
        "critical_windows": [{"name": "harvest_drying", "months": [8, 9], "risk_factors": ["heavy_rain", "humidity"]}],
    },
    "apple": {
        "storage_type": "storage",
        "cultivation_type": ["open_field", "stored"],
        "growth_calendar": {"flowering": [4, 5], "fruit_growth": [6, 7, 8]},
        "harvest_calendar": {"main": [9, 10, 11]},
        "weather": {"heat": 0.65, "cold": 0.7, "heavy_rain": 0.65, "drought": 0.45, "wind": 0.7, "sunshine": 0.65},
        "critical_windows": [{"name": "flowering_and_fruit", "months": [4, 5, 8, 9], "risk_factors": ["cold", "wind", "heavy_rain", "sunshine"]}],
    },
    "pear": {
        "storage_type": "storage",
        "cultivation_type": ["open_field", "stored"],
        "growth_calendar": {"flowering": [4, 5], "fruit_growth": [6, 7, 8]},
        "harvest_calendar": {"main": [9, 10]},
        "weather": {"heat": 0.6, "cold": 0.7, "heavy_rain": 0.65, "drought": 0.45, "wind": 0.75, "sunshine": 0.6},
        "critical_windows": [{"name": "fruit_quality", "months": [4, 5, 8, 9], "risk_factors": ["cold", "wind", "heavy_rain", "sunshine"]}],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate draft item metadata from a KAMIS candidate audit.")
    parser.add_argument("--audit", required=True)
    parser.add_argument("--status", nargs="*", default=["ready"])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    ui_meta = parse_ui_item_meta(INDEX_HTML_PATH)
    created = []
    skipped = []
    for row in audit.get("items", []):
        item_code = str(row.get("item_code") or "")
        if row.get("already_mapped") or row.get("status") not in set(args.status):
            skipped.append({"item_code": item_code, "reason": "already_mapped_or_status"})
            continue
        best = row.get("best_variant")
        if not isinstance(best, dict):
            skipped.append({"item_code": item_code, "reason": "missing_best_variant"})
            continue
        output = ITEMS_DIR / f"{item_code}.json"
        if output.exists() and not args.overwrite:
            skipped.append({"item_code": item_code, "reason": "exists"})
            continue
        meta = build_metadata(row, best, ui_meta.get(item_code, {}))
        output.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(str(output.relative_to(REPO_ROOT)))
    print(json.dumps({"ok": True, "created": created, "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0


def parse_ui_item_meta(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"const\s+ITEMS\s*=\s*\{(?P<body>.*?)\n\};", text, flags=re.S)
    if not match:
        return {}
    rows = {}
    pattern = re.compile(
        r"^\s*(?P<code>[A-Za-z0-9_]+)\s*:\s*\{"
        r"(?=.*?name:\"(?P<name>[^\"]+)\")"
        r"(?=.*?unit:\"(?P<unit>[^\"]+)\")"
        r"(?=.*?hotspot:\"(?P<hotspot>[^\"]+)\")",
        flags=re.M,
    )
    for item in pattern.finditer(match.group("body")):
        rows[item.group("code")] = {
            "name": item.group("name"),
            "unit": item.group("unit"),
            "hotspot": item.group("hotspot"),
        }
    return rows


def build_metadata(row: dict[str, Any], best: dict[str, Any], ui: dict[str, str]) -> dict[str, Any]:
    item_code = str(row["item_code"])
    profile = ITEM_PROFILE_OVERRIDES.get(item_code, default_profile())
    item_name = str(row["item_name"])
    hotspot = ui.get("hotspot") or "전국"
    region_code = PROVINCE_CODES.get(hotspot, "00")
    variants = []
    for variant in row.get("tested_variants", []):
        if not isinstance(variant, dict) or int(variant.get("feature_count") or 0) <= 0:
            continue
        variants.append(
            {
                "kindcode": str(variant["kindcode"]),
                "kind_name": str(variant["kind_name"]),
                "primary": str(variant["kindcode"]) == str(best["kindcode"]),
            }
        )
    if not variants:
        variants = [{"kindcode": str(best["kindcode"]), "kind_name": str(best["kind_name"]), "primary": True}]

    return {
        "item_code": item_code,
        "item_name": item_name,
        "category": str(best.get("category_name") or "미분류"),
        "aliases": [],
        "external_mappings": {
            "kamis_price": {
                "mapping_status": "candidate_verified_recent_price",
                "itemcategorycode": str(best["category_code"]),
                "itemcode": str(best["itemcode"]),
                "productrankcode": "04",
                "variants": variants,
                "product_classes": ["01", "02"],
                "notes": "Generated from KAMIS codebook and live recent-price audit. Confirm variety choice before production promotion.",
            },
            "kma_crop_weather": {
                "mapping_status": "candidate_regions_only",
                "candidate_regions": [hotspot],
                "notes": "KMA crop-weather PA_CROP_SPE_ID and AREA_ID are not verified yet for this generated item.",
            },
        },
        "crop_profile": {
            "storage_type": profile["storage_type"],
            "cultivation_type": profile["cultivation_type"],
            "growth_calendar": profile["growth_calendar"],
            "harvest_calendar": profile["harvest_calendar"],
            "demand_events": profile.get("demand_events", []),
            "substitute_items": profile.get("substitute_items", []),
        },
        "production_profile": {
            "region_strategy": "manual_weighted",
            "manual_regions": [
                {
                    "region_code": region_code,
                    "region_name": hotspot,
                    "base_weight": 0.5,
                    "notes": "UI hotspot based seed region. Replace with KOSIS/FarmMap production shares after source verification.",
                }
            ],
        },
        "market_profile": {
            "price_volatility": profile.get("price_volatility", "medium"),
            "price_lag_days": profile.get("price_lag_days", 7),
            "market_sensitivity": {
                "retail_price": 0.3,
                "wholesale_price": 0.45,
                "settlement_volume": 0.25,
            },
        },
        "weather_profile": {
            "sensitivity": profile["weather"],
            "critical_windows": profile["critical_windows"],
        },
        "event_profile": {
            "enabled_events": ["weather_alert", "impact_forecast", "typhoon", "midterm_forecast"],
            "event_weights": {
                "weather_alert": 0.3,
                "impact_forecast": 0.2,
                "typhoon": 0.25,
                "midterm_forecast": 0.25,
            },
        },
        "feature_engine_profile": {
            "engine_set": [
                "item_meta",
                "production_region",
                "price_market",
                "agri_weather",
                "disaster_event",
                "forecast_context",
                "risk_signal",
            ],
            "feature_overrides": {
                "risk_signal": {
                    "market_pressure_weight": 0.4,
                    "weather_pressure_weight": 0.25,
                    "event_pressure_weight": 0.15,
                }
            },
        },
        "source_coverage": {
            "kamis": True,
            "kosis": False,
            "data_go_kr": ["at_regional_price", "weather_alert", "impact_forecast", "typhoon", "midterm_forecast"],
            "manual_review_required": True,
        },
    }


def default_profile() -> dict[str, Any]:
    return {
        "storage_type": "fresh",
        "cultivation_type": ["open_field"],
        "growth_calendar": {"main": [3, 4, 5, 6, 7, 8]},
        "harvest_calendar": {"main": [6, 7, 8, 9, 10]},
        "weather": {"heat": 0.6, "cold": 0.45, "heavy_rain": 0.65, "drought": 0.45, "humidity": 0.6},
        "critical_windows": [{"name": "main_growth", "months": [6, 7, 8], "risk_factors": ["heat", "heavy_rain", "humidity"]}],
    }


if __name__ == "__main__":
    raise SystemExit(main())
