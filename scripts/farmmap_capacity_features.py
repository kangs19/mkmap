from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CITY_AGRI_DATA_PATH = REPO_ROOT / "map_viewer" / "static" / "city_agri_data.json"
LOCAL_DB_CANDIDATES = [
    REPO_ROOT / "backend" / "agri_twin.db",
    REPO_ROOT / "agri_twin.db",
]

FARMMAP_FEATURE_COLUMNS = [
    "farmmap_capacity_score_norm",
    "farmmap_capacity_match_ratio",
    "farmmap_capacity_high_conf_ratio",
    "farmmap_crop_to_landuse_ratio",
    "farmmap_agri_landuse_area_norm",
    "farmmap_missing_flag",
]

SIDO_FULL_NAMES = {
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "제주": "제주특별자치도",
    "전남": "전라남도",
    "전북": "전북특별자치도",
    "경북": "경상북도",
    "경남": "경상남도",
    "경기": "경기도",
    "충남": "충청남도",
}

AGRI_LANDUSE_CLASSES = {"밭", "논", "시설", "과수"}


def default_farmmap_capacity_features() -> dict[str, float]:
    return {
        "farmmap_capacity_score_norm": 0.0,
        "farmmap_capacity_match_ratio": 0.0,
        "farmmap_capacity_high_conf_ratio": 0.0,
        "farmmap_crop_to_landuse_ratio": 0.0,
        "farmmap_agri_landuse_area_norm": 0.0,
        "farmmap_missing_flag": 1.0,
    }


def load_farmmap_capacity_features_by_item(repo_root: Path = REPO_ROOT) -> dict[str, dict[str, float]]:
    """Build item-level FarmMap capacity priors for price-model training.

    The current price table is item/date based, not region/date based, so these
    features are static item priors repeated across dates. They combine crop
    metadata production weights with verified FarmMap land-use summaries.
    """

    city_data = _load_city_agri_data(repo_root)
    landuse = _load_landuse_from_local_db(repo_root)
    features: dict[str, dict[str, float]] = {}
    for item_code, item_regions in city_data.items():
        if isinstance(item_regions, dict):
            features[item_code] = _item_capacity_features(item_regions, landuse)
    return features


def _item_capacity_features(
    item_regions: dict[str, Any],
    landuse: dict[str, dict],
) -> dict[str, float]:
    defaults = default_farmmap_capacity_features()
    regions = [row for row in item_regions.values() if isinstance(row, dict)]
    if not regions:
        return defaults

    total_production = sum(_as_float(row.get("production_ton")) for row in regions)
    max_production = max((_as_float(row.get("production_ton")) for row in regions), default=0.0)
    prepared: list[dict[str, Any]] = []
    max_agri_area = 0.0

    for row in regions:
        short_sido = str(row.get("sido") or "")
        full_sido = SIDO_FULL_NAMES.get(short_sido, short_sido)
        sigungu = str(row.get("name") or "")
        exact = landuse["city"].get((full_sido, sigungu))
        province = landuse["province"].get(full_sido)
        matched = exact or province
        match_level = "sigungu" if exact else "province" if province else None
        if exact:
            max_agri_area = max(max_agri_area, _as_float(exact.get("agri_area_ha")))
        prepared.append(
            {
                "production_ton": _as_float(row.get("production_ton")),
                "crop_area_ha": _as_float(row.get("area_ha")),
                "landuse": matched,
                "match_level": match_level,
            }
        )

    if max_agri_area <= 0:
        max_agri_area = max(
            (_as_float((row.get("landuse") or {}).get("agri_area_ha")) for row in prepared),
            default=0.0,
        )

    weighted_score = 0.0
    weighted_match = 0.0
    weighted_high_conf = 0.0
    weighted_crop_ratio = 0.0
    weighted_agri_norm = 0.0
    matched_weight = 0.0

    for row in prepared:
        weight = _region_weight(row, total_production, len(prepared))
        production = row["production_ton"]
        crop_area = row["crop_area_ha"]
        production_norm = production / max_production if max_production else 0.0
        landuse_summary = row.get("landuse") or {}
        agri_area = _as_float(landuse_summary.get("agri_area_ha"))
        agri_norm = agri_area / max_agri_area if max_agri_area else 0.0
        crop_landuse_ratio = min(crop_area / agri_area, 1.0) if agri_area else 0.0

        if row["match_level"] == "sigungu":
            score = 65 * production_norm + 25 * agri_norm + 10 * crop_landuse_ratio
            weighted_match += weight
            weighted_high_conf += weight
            matched_weight += weight
            weighted_crop_ratio += weight * crop_landuse_ratio
            weighted_agri_norm += weight * agri_norm
        elif row["match_level"] == "province":
            score = 75 * production_norm + 10 * agri_norm
            weighted_match += weight
            matched_weight += weight
            weighted_agri_norm += weight * agri_norm
        else:
            score = 65 * production_norm

        weighted_score += weight * max(0.0, min(100.0, score)) / 100.0

    if matched_weight <= 0:
        defaults["farmmap_capacity_score_norm"] = round(weighted_score, 6)
        return defaults

    return {
        "farmmap_capacity_score_norm": round(weighted_score, 6),
        "farmmap_capacity_match_ratio": round(weighted_match, 6),
        "farmmap_capacity_high_conf_ratio": round(weighted_high_conf, 6),
        "farmmap_crop_to_landuse_ratio": round(weighted_crop_ratio / matched_weight, 6),
        "farmmap_agri_landuse_area_norm": round(weighted_agri_norm / matched_weight, 6),
        "farmmap_missing_flag": 0.0,
    }


def _load_city_agri_data(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "map_viewer" / "static" / "city_agri_data.json"
    if not path.exists():
        path = CITY_AGRI_DATA_PATH
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_landuse_from_local_db(repo_root: Path) -> dict[str, dict]:
    city: dict[tuple[str, str], dict] = {}
    province: dict[str, dict] = {}
    db_path = next((path for path in [repo_root / "backend" / "agri_twin.db", *LOCAL_DB_CANDIDATES] if path.exists()), None)
    if db_path is None:
        return {"city": city, "province": province}

    try:
        with sqlite3.connect(db_path) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                """
                SELECT sido, sigungu, landuse_class, parcel_count, area_ha
                FROM farmmap_landuse_regions
                """
            ).fetchall()
    except sqlite3.Error:
        return {"city": city, "province": province}

    for row in rows:
        sido = str(row["sido"] or "")
        sigungu = str(row["sigungu"] or "")
        if sigungu:
            key = (sido, sigungu)
            city.setdefault(key, _empty_landuse_summary(sido, sigungu))
            _add_landuse(city[key], row)
        province.setdefault(sido, _empty_landuse_summary(sido, None))
        _add_landuse(province[sido], row)

    return {"city": city, "province": province}


def _empty_landuse_summary(sido: str, sigungu: str | None) -> dict[str, Any]:
    return {
        "sido": sido,
        "sigungu": sigungu,
        "area_ha": 0.0,
        "agri_area_ha": 0.0,
        "parcel_count": 0,
    }


def _add_landuse(summary: dict[str, Any], row: sqlite3.Row) -> None:
    area = _as_float(row["area_ha"])
    summary["area_ha"] += area
    summary["parcel_count"] += int(_as_float(row["parcel_count"]))
    if str(row["landuse_class"] or "") in AGRI_LANDUSE_CLASSES:
        summary["agri_area_ha"] += area


def _region_weight(row: dict[str, Any], total_production: float, region_count: int) -> float:
    if total_production > 0:
        return _as_float(row.get("production_ton")) / total_production
    return 1.0 / region_count if region_count else 0.0


def _as_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


if __name__ == "__main__":
    payload = load_farmmap_capacity_features_by_item()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
