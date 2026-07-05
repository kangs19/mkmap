from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from sqlalchemy import select, and_
from pathlib import Path
import json
from datetime import date, timedelta
from app.database import get_db
from app.models.signal import RegionSignal
from app.models.price import DailyPrice
from app.models.production import CropProduction
from app.timezone import kst_today
from app.models.regional_price import RegionalMarketPrice
from app.models.farmmap import FarmMapCropRegion, FarmMapLanduseRegion

router = APIRouter(tags=["maps"])

TEMPLATES = Path(__file__).parent.parent.parent.parent / "map_viewer" / "templates"
TEMPLATE_PATH = TEMPLATES / "item_map.html"
DASHBOARD_PATH = TEMPLATES / "dashboard.html"
WIDGET_PATH    = TEMPLATES / "widget.html"
ADMIN_PATH     = TEMPLATES / "admin.html"
FORECAST_EXPLANATION_PATH = TEMPLATES / "forecast_explanation.html"
PERFORMANCE_PATH = TEMPLATES / "performance.html"

ITEM_NAMES = {
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "green_onion": "대파",
    "garlic": "마늘",
}

CITY_AGRI_DATA_PATHS = [
    Path(__file__).resolve().parents[3] / "map_viewer" / "static" / "city_agri_data.json",
    Path("/app/map_viewer/static/city_agri_data.json"),
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


def _load_city_agri_data() -> dict:
    for path in CITY_AGRI_DATA_PATHS:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _empty_landuse_summary(sido: str | None = None, sigungu: str | None = None) -> dict:
    return {
        "sido": sido,
        "sigungu": sigungu,
        "area_ha": 0.0,
        "agri_area_ha": 0.0,
        "parcel_count": 0,
        "classes": {},
    }


def _add_landuse(summary: dict, row: FarmMapLanduseRegion) -> None:
    area = float(row.area_ha or 0.0)
    summary["area_ha"] += area
    summary["parcel_count"] += int(row.parcel_count or 0)
    summary["classes"][row.landuse_class] = summary["classes"].get(row.landuse_class, 0.0) + area
    if row.landuse_class in AGRI_LANDUSE_CLASSES:
        summary["agri_area_ha"] += area


def _finalize_landuse(summary: dict | None) -> dict | None:
    if not summary:
        return None
    classes = summary.get("classes") or {}
    top_class = sorted(classes.items(), key=lambda item: item[1], reverse=True)[0][0] if classes else None
    return {
        "sido": summary.get("sido"),
        "sigungu": summary.get("sigungu"),
        "total_area_ha": round(summary.get("area_ha", 0.0), 4),
        "agri_area_ha": round(summary.get("agri_area_ha", 0.0), 4),
        "parcel_count": summary.get("parcel_count") or 0,
        "top_class": top_class,
        "class_totals_ha": {
            key: round(value, 4)
            for key, value in sorted(classes.items(), key=lambda item: item[1], reverse=True)
        },
    }


def _capacity_label(score: int | None, confidence: str) -> str:
    if score is None:
        return "insufficient_data"
    if confidence == "crop_only":
        return "crop_metadata_only"
    if score >= 75:
        return "strong"
    if score >= 50:
        return "moderate"
    return "limited"


@router.get("/admin/ui", response_class=HTMLResponse)
async def get_admin_ui(request: Request):
    """관리자 대시보드 UI"""
    html = ADMIN_PATH.read_text(encoding="utf-8")
    api_base = str(request.base_url).rstrip("/")
    html = html.replace('const API_BASE = "";', f'const API_BASE = "{api_base}";')
    return HTMLResponse(content=html)


@router.get("/maps/items/{item_code}", response_class=HTMLResponse)
async def get_item_map(request: Request, item_code: str):
    item_name = ITEM_NAMES.get(item_code, item_code)
    api_base = str(request.base_url).rstrip("/")

    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = html.replace("{{ item_code }}", item_code)
    html = html.replace("{{ item_name }}", item_name)
    html = html.replace("{{ api_base }}", api_base)

    return HTMLResponse(content=html)


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    html = DASHBOARD_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/performance", response_class=HTMLResponse)
async def get_performance_page(request: Request):
    """공개 모델 성능 페이지 — admin key 불필요"""
    html = PERFORMANCE_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@router.get("/forecast-explanation", response_class=HTMLResponse)
async def get_forecast_explanation(request: Request):
    html = FORECAST_EXPLANATION_PATH.read_text(encoding="utf-8")
    api_base = str(request.base_url).rstrip("/")
    html = html.replace("{{ api_base }}", api_base)
    return HTMLResponse(content=html)


@router.get("/widget", response_class=HTMLResponse)
async def get_widget(request: Request, item: str = "cabbage"):
    """WordPress iframe 임베드용 위젯 — ?item=cabbage|radish|onion|green_onion|garlic"""
    html = WIDGET_PATH.read_text(encoding="utf-8")
    # API_BASE를 서버 자신의 URL로 주입
    api_base = str(request.base_url).rstrip("/")
    html = html.replace(
        'const API_BASE = (function() {',
        f'const _INJECTED_API_BASE = "{api_base}";\nconst API_BASE = (function() {{'
    ).replace(
        '})() || "";',
        f'}})() || _INJECTED_API_BASE;'
    )
    return HTMLResponse(content=html)


@router.get("/widget/embed", response_class=HTMLResponse)
async def get_widget_embed_guide(request: Request):
    """WordPress 임베드 가이드 — iframe 코드 + 단축코드 예시"""
    base = str(request.base_url).rstrip("/")
    guide = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>WordPress 임베드 가이드</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:40px auto;padding:20px;}}
pre{{background:#f4f4f4;padding:16px;border-radius:6px;overflow-x:auto;font-size:13px;}}
h2{{margin-top:32px;}}code{{background:#eee;padding:2px 6px;border-radius:3px;}}</style>
</head><body>
<h1>🌾 WordPress iframe 임베드 가이드</h1>
<p>아래 코드를 WordPress 페이지 편집기(HTML 모드)에 붙여넣으세요.</p>

<h2>📌 기본 위젯 (배추 기본값)</h2>
<pre>&lt;iframe src="{base}/widget"
  width="100%" height="380"
  frameborder="0" scrolling="no"
  style="border-radius:10px;max-width:480px;display:block;"&gt;
&lt;/iframe&gt;</pre>

<h2>📌 품목 지정 임베드</h2>
<pre>&lt;!-- 배추 --&gt;
&lt;iframe src="{base}/widget?item=cabbage" width="480" height="380" frameborder="0"&gt;&lt;/iframe&gt;

&lt;!-- 양파 --&gt;
&lt;iframe src="{base}/widget?item=onion" width="480" height="380" frameborder="0"&gt;&lt;/iframe&gt;

&lt;!-- 마늘 --&gt;
&lt;iframe src="{base}/widget?item=garlic" width="480" height="380" frameborder="0"&gt;&lt;/iframe&gt;</pre>

<h2>📌 반응형 임베드 (권장)</h2>
<pre>&lt;div style="position:relative;padding-bottom:80%;height:0;overflow:hidden;max-width:480px;"&gt;
  &lt;iframe src="{base}/widget"
    style="position:absolute;top:0;left:0;width:100%;height:100%;border-radius:10px;"
    frameborder="0"&gt;&lt;/iframe&gt;
&lt;/div&gt;</pre>

<h2>📡 API 직접 연동</h2>
<pre>// 전체 예측 데이터
GET {base}/api/v1/signals/today

// 품목별 예측
GET {base}/api/v1/items/cabbage/forecast

// 지역 위험 신호
GET {base}/api/v1/map/signals?item_code=cabbage

// 일일 리포트
GET {base}/api/v1/report/today</pre>
</body></html>"""
    return HTMLResponse(content=guide)


@router.get("/api/v1/drought")
async def get_drought_index(db: AsyncSession = Depends(get_db)):
    """전국 농업용수 저수율 가뭄 지표 (MAFRA 669). 최신 + 최근 추이."""
    from app.models.drought import DroughtIndex
    rows = (await db.execute(
        select(DroughtIndex).order_by(DroughtIndex.base_ym.desc()).limit(4)
    )).scalars().all()
    if not rows:
        return {"available": False}
    latest = rows[0]
    trend = [
        {"ym": r.base_ym, "reservoir_rate": r.reservoir_rate}
        for r in reversed(rows)
    ]
    # 저수율 수준 라벨 (농업용수 기준 통상 50% 미만 주의, 40% 미만 경계)
    r = latest.reservoir_rate or 0
    if r >= 60:
        level, label = "normal", "정상"
    elif r >= 50:
        level, label = "watch", "주의"
    elif r >= 40:
        level, label = "caution", "경계"
    else:
        level, label = "alert", "심각"
    return {
        "available": True,
        "base_ym": latest.base_ym,
        "reservoir_rate": latest.reservoir_rate,
        "rainfall_avg": latest.rainfall_avg,
        "region_count": latest.region_count,
        "level": level, "level_label": label,
        "trend": trend,
        "note": "전국 농업용수 저수율 평균. 저수율이 낮으면 가뭄으로 공급 감소·가격 상승 위험이 있습니다.",
    }


@router.get("/api/v1/map/signals")
async def get_map_signals(
    item_code: str = "cabbage",
    target_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    """지도용 — 품목별 전국 지역 위험 신호 (Leaflet 직접 소비)"""
    base_date = date.fromisoformat(target_date) if target_date else kst_today()

    result = await db.execute(
        select(RegionSignal).where(
            and_(RegionSignal.item_code == item_code, RegionSignal.date == base_date)
        ).order_by(RegionSignal.risk_score.desc())
    )
    signals = result.scalars().all()

    # 신호 없으면 가장 최근 날짜로 fallback
    if not signals:
        latest = await db.execute(
            select(RegionSignal.date)
            .where(RegionSignal.item_code == item_code)
            .order_by(RegionSignal.date.desc())
            .limit(1)
        )
        latest_date = latest.scalar_one_or_none()
        if latest_date:
            result2 = await db.execute(
                select(RegionSignal).where(
                    and_(RegionSignal.item_code == item_code, RegionSignal.date == latest_date)
                )
            )
            signals = result2.scalars().all()
            base_date = latest_date

    return {
        "item_code": item_code,
        "base_date": str(base_date),
        "regions": [
            {
                "region_code": s.region_code,
                "region_name": s.region_name,
                "risk_score": s.risk_score,
                "risk_level": s.risk_level,
                "price_effect": s.price_effect,
                "summary": s.summary_text,
                "weather": s.weather_summary,
                "market": s.market_summary,
            }
            for s in signals
        ],
    }


@router.get("/api/v1/map/prices")
async def get_map_prices(
    item_code: str = "cabbage",
    db: AsyncSession = Depends(get_db),
):
    """지도용 — 최근 30일 가격 추이"""
    from datetime import timedelta
    end = kst_today()
    start = end - timedelta(days=30)

    result = await db.execute(
        select(DailyPrice).where(
            and_(DailyPrice.item_code == item_code,
                 DailyPrice.date >= start)
        ).order_by(DailyPrice.date)
    )
    rows = result.scalars().all()
    return {
        "item_code": item_code,
        "prices": [
            {
                "date": str(r.date),
                "price": r.wholesale_price,
                "avg_year": r.avg_year_price,
                "prev_year": r.prev_year_price,
                "source": r.source,
            }
            for r in rows
        ],
    }


@router.get("/api/v1/map/production")
async def get_map_production(
    item_code: str = "cabbage",
    db: AsyncSession = Depends(get_db),
):
    """지도용 — KOSIS 연간 재배면적·생산량 (미완결/부분수집 연도 제외)"""
    import statistics as _st
    result = await db.execute(
        select(CropProduction)
        .where(CropProduction.item_code == item_code)
        .order_by(CropProduction.year.desc())
        .limit(8)
    )
    rows = list(result.scalars().all())
    # 부분수집(미완결) 연도 제외: 생산량이 최근 연도 중앙값의 40% 미만이면 불완전으로 간주
    prods = [r.production_ton for r in rows if r.production_ton and r.production_ton > 0]
    if len(prods) >= 3:
        med = _st.median(prods)
        rows = [
            r for r in rows
            if not (r.production_ton and med > 0 and r.production_ton < med * 0.4)
        ]
    rows = rows[:5]
    return {
        "item_code": item_code,
        "production": [
            {
                "year": r.year,
                "area_ha": r.area_ha,
                "production_ton": r.production_ton,
                "source": r.source,
            }
            for r in rows
        ],
    }


@router.get("/api/v1/map/farmmap/crop-regions")
async def get_farmmap_crop_regions(
    item_code: str = "cabbage",
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(FarmMapCropRegion)
        .where(FarmMapCropRegion.item_code == item_code)
        .order_by(FarmMapCropRegion.area_ha.desc().nullslast(), FarmMapCropRegion.farm_count.desc().nullslast())
    )).scalars().all()
    if not rows:
        return {
            "item_code": item_code,
            "available": False,
            "regions": [],
            "source": "farmmap",
            "note": "FarmMap source files have not been imported for this item yet.",
        }

    total_area_ha = sum(float(row.area_ha or 0.0) for row in rows)
    total_farm_count = sum(int(row.farm_count or 0) for row in rows)
    return {
        "item_code": item_code,
        "available": True,
        "source": "farmmap",
        "region_count": len(rows),
        "total_area_ha": round(total_area_ha, 4) if total_area_ha else None,
        "total_farm_count": total_farm_count or None,
        "regions": [
            {
                "sido": row.sido,
                "sigungu": row.sigungu,
                "region_code": row.region_code,
                "source_crop_name": row.source_crop_name,
                "farm_count": row.farm_count,
                "area_m2": row.area_m2,
                "area_ha": row.area_ha,
                "area_share_pct": (
                    round(float(row.area_ha or 0.0) / total_area_ha * 100.0, 2)
                    if total_area_ha and row.area_ha is not None
                    else None
                ),
                "geometry_level": row.geometry_level,
                "source_file": row.source_file,
                "source_year": row.source_year,
                "confidence": row.confidence,
            }
            for row in rows
        ],
    }


@router.get("/api/v1/map/farmmap/landuse-regions")
async def get_farmmap_landuse_regions(
    sido: str | None = None,
    landuse_class: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if sido:
        conditions.append(FarmMapLanduseRegion.sido == sido)
    if landuse_class:
        conditions.append(FarmMapLanduseRegion.landuse_class == landuse_class)

    query = select(FarmMapLanduseRegion)
    if conditions:
        query = query.where(and_(*conditions))
    rows = (await db.execute(
        query.order_by(FarmMapLanduseRegion.area_ha.desc().nullslast(), FarmMapLanduseRegion.parcel_count.desc().nullslast())
    )).scalars().all()

    if not rows:
        return {
            "available": False,
            "source": "farmmap",
            "source_type": "landuse_only",
            "regions": [],
            "note": "FarmMap land-use summaries have not been imported yet.",
        }

    total_area_ha = sum(float(row.area_ha or 0.0) for row in rows)
    total_parcel_count = sum(int(row.parcel_count or 0) for row in rows)
    class_totals: dict[str, float] = {}
    for row in rows:
        class_totals[row.landuse_class] = class_totals.get(row.landuse_class, 0.0) + float(row.area_ha or 0.0)

    return {
        "available": True,
        "source": "farmmap",
        "source_type": "landuse_only",
        "sido": sido,
        "landuse_class": landuse_class,
        "region_count": len(rows),
        "total_area_ha": round(total_area_ha, 4) if total_area_ha else None,
        "total_parcel_count": total_parcel_count or None,
        "class_totals_ha": {
            key: round(value, 4)
            for key, value in sorted(class_totals.items(), key=lambda item: item[1], reverse=True)
        },
        "regions": [
            {
                "sido": row.sido,
                "sigungu": row.sigungu,
                "landuse_class": row.landuse_class,
                "parcel_count": row.parcel_count,
                "area_m2": row.area_m2,
                "area_ha": row.area_ha,
                "area_share_pct": (
                    round(float(row.area_ha or 0.0) / total_area_ha * 100.0, 2)
                    if total_area_ha and row.area_ha is not None
                    else None
                ),
                "source_file": row.source_file,
                "confidence": row.confidence,
            }
            for row in rows
        ],
    }


@router.get("/api/v1/map/farmmap/crop-capacity")
async def get_farmmap_crop_capacity(
    item_code: str = "cabbage",
    db: AsyncSession = Depends(get_db),
):
    """Crop-region capacity score from crop metadata plus official FarmMap land-use.

    This is not a price forecast and not crop-specific FarmMap acreage. It is a
    source-labeled support feature: crop production metadata supplies crop
    relevance, while FarmMap land-use supplies verified agricultural land context.
    """

    city_data = _load_city_agri_data()
    item_regions = city_data.get(item_code) or {}
    if not item_regions:
        return {
            "item_code": item_code,
            "available": False,
            "source_type": "crop_metadata_plus_farmmap_landuse",
            "regions": [],
            "note": "No city-level crop metadata is available for this item.",
        }

    landuse_rows = (await db.execute(select(FarmMapLanduseRegion))).scalars().all()
    city_landuse: dict[tuple[str, str], dict] = {}
    province_landuse: dict[str, dict] = {}
    for row in landuse_rows:
        if row.sigungu:
            key = (row.sido, row.sigungu)
            city_landuse.setdefault(key, _empty_landuse_summary(row.sido, row.sigungu))
            _add_landuse(city_landuse[key], row)
        province_landuse.setdefault(row.sido, _empty_landuse_summary(row.sido, None))
        _add_landuse(province_landuse[row.sido], row)

    total_production = sum(float(region.get("production_ton") or 0.0) for region in item_regions.values())
    max_production = max((float(region.get("production_ton") or 0.0) for region in item_regions.values()), default=0.0)

    prepared: list[dict] = []
    max_agri_area = 0.0
    for region_code, region in item_regions.items():
        short_sido = region.get("sido") or ""
        full_sido = SIDO_FULL_NAMES.get(short_sido, short_sido)
        sigungu = region.get("name") or ""
        exact = city_landuse.get((full_sido, sigungu))
        province = province_landuse.get(full_sido)
        matched = exact or province
        match_level = "sigungu" if exact else "province" if province else None
        if exact:
            max_agri_area = max(max_agri_area, float(exact.get("agri_area_ha") or 0.0))
        prepared.append({
            "region_code": region_code,
            "region_name": sigungu,
            "sido": short_sido,
            "sido_full": full_sido,
            "production_ton": float(region.get("production_ton") or 0.0),
            "crop_area_ha": float(region.get("area_ha") or 0.0),
            "shipment_yoy": region.get("shipment_yoy"),
            "price_index": region.get("price_index"),
            "landuse": matched,
            "match_level": match_level,
        })

    if max_agri_area <= 0:
        max_agri_area = max((float((row.get("landuse") or {}).get("agri_area_ha") or 0.0) for row in prepared), default=0.0)

    regions = []
    exact_matches = 0
    province_matches = 0
    for row in prepared:
        production = row["production_ton"]
        crop_area = row["crop_area_ha"]
        production_share_pct = round(production / total_production * 100.0, 2) if total_production else None
        production_norm = production / max_production if max_production else 0.0
        landuse_summary = _finalize_landuse(row["landuse"])
        agri_area = float((row["landuse"] or {}).get("agri_area_ha") or 0.0)
        agri_norm = agri_area / max_agri_area if max_agri_area else 0.0
        crop_landuse_ratio = min(crop_area / agri_area, 1.0) if agri_area else None

        if row["match_level"] == "sigungu":
            exact_matches += 1
            confidence = "high"
            score = round(65 * production_norm + 25 * agri_norm + 10 * (crop_landuse_ratio or 0.0))
        elif row["match_level"] == "province":
            province_matches += 1
            confidence = "medium"
            score = round(75 * production_norm + 10 * agri_norm)
        else:
            confidence = "crop_only"
            score = round(65 * production_norm) if production_norm else None

        if score is not None:
            score = max(0, min(100, int(score)))

        regions.append({
            "region_code": row["region_code"],
            "region_name": row["region_name"],
            "sido": row["sido"],
            "sido_full": row["sido_full"],
            "crop_area_ha": round(crop_area, 4),
            "production_ton": round(production, 4),
            "production_share_pct": production_share_pct,
            "shipment_yoy": row["shipment_yoy"],
            "price_index": row["price_index"],
            "farmmap_match_level": row["match_level"],
            "farmmap_landuse": landuse_summary,
            "crop_to_agri_landuse_ratio": round(crop_landuse_ratio, 4) if crop_landuse_ratio is not None else None,
            "capacity_score": score,
            "capacity_label": _capacity_label(score, confidence),
            "confidence": confidence,
            "source_notes": [
                "crop metadata: map_viewer/static/city_agri_data.json",
                "FarmMap: official land-use summary, not crop-specific acreage",
            ] if row["match_level"] else [
                "crop metadata only; FarmMap land-use not imported for this region",
            ],
        })

    regions.sort(
        key=lambda item: (
            item["capacity_score"] is not None,
            item["capacity_score"] or -1,
            item["production_ton"],
        ),
        reverse=True,
    )

    return {
        "item_code": item_code,
        "available": True,
        "source_type": "crop_metadata_plus_farmmap_landuse",
        "score_meaning": "regional crop capacity/support signal; not a price forecast and not FarmMap crop acreage",
        "farmmap_available": bool(landuse_rows),
        "region_count": len(regions),
        "matched_region_count": exact_matches,
        "province_fallback_count": province_matches,
        "total_production_ton": round(total_production, 4) if total_production else None,
        "regions": regions,
    }


@router.get("/api/v1/model/champion-challenger")
async def get_champion_challenger():
    """가격모델 v1 vs v2(물량·날씨 피처) 홀드아웃 정확도 비교 결과."""
    import json as _json
    from pathlib import Path as _Path
    p = _Path(__file__).resolve().parents[3] / "data" / "model" / "champion_challenger.json"
    if not p.exists():
        return {"available": False, "note": "아직 파이프라인이 v2 비교를 실행하지 않음"}
    try:
        return {"available": True, **_json.loads(p.read_text(encoding="utf-8"))}
    except Exception as e:
        return {"available": False, "error": str(e)[:120]}


@router.get("/api/v1/map/shipment-share")
async def get_shipment_share(item_code: str = "cabbage", db: AsyncSession = Depends(get_db)):
    """실시간 경매 산지 기반 시도별 출하 비중 (하드코딩 생산비중 대체)."""
    from app.models.shipment import ShipmentShare
    rows = (await db.execute(
        select(ShipmentShare).where(ShipmentShare.item_code == item_code)
        .order_by(ShipmentShare.share_pct.desc())
    )).scalars().all()
    if not rows:
        return {"item_code": item_code, "available": False, "shares": {}}
    return {
        "item_code": item_code,
        "available": True,
        "base_date": str(rows[0].base_date),
        "shares": {r.sido: r.share_pct for r in rows},
        "note": "최근 7일 도매시장 경매 산지별 출하량 비중 (계절 반영)",
    }


@router.get("/api/v1/map/regional-prices")
async def get_regional_prices(
    item_code: str = "cabbage",
    db: AsyncSession = Depends(get_db),
):
    """지역별 최신 도매가·소매가 — 지도 choropleth 용"""
    from sqlalchemy import func as sqlfunc

    # 각 (item_code, market_code) 조합의 최신 날짜
    subq = (
        select(
            RegionalMarketPrice.item_code,
            RegionalMarketPrice.market_code,
            sqlfunc.max(RegionalMarketPrice.date).label("max_date"),
        )
        .where(RegionalMarketPrice.item_code == item_code)
        .group_by(RegionalMarketPrice.item_code, RegionalMarketPrice.market_code)
        .subquery()
    )
    result = await db.execute(
        select(RegionalMarketPrice).join(
            subq,
            (RegionalMarketPrice.item_code   == subq.c.item_code)
            & (RegionalMarketPrice.market_code == subq.c.market_code)
            & (RegionalMarketPrice.date        == subq.c.max_date)
        )
    )
    rows = result.scalars().all()

    if not rows:
        return {"item_code": item_code, "base_date": None, "markets": [], "sido_avg": {}}

    # 시도별 평균 (복수 시장이 같은 시도 커버하는 경우)
    from collections import defaultdict
    sido_ws: dict[str, list] = defaultdict(list)
    sido_rt: dict[str, list] = defaultdict(list)
    market_list = []
    for r in rows:
        market_list.append({
            "market_code":      r.market_code,
            "market_name":      r.market_name,
            "sido":             r.sido,
            "date":             str(r.date),
            "wholesale_price":  r.wholesale_price,
            "retail_price":     r.retail_price,
        })
        if r.wholesale_price:
            sido_ws[r.sido].append(r.wholesale_price)
        if r.retail_price:
            sido_rt[r.sido].append(r.retail_price)

    sido_avg = {}
    for sido, ws in sido_ws.items():
        ws_avg = round(sum(ws) / len(ws))
        rt_list = sido_rt.get(sido, [])
        rt_avg = round(sum(rt_list) / len(rt_list)) if rt_list else None
        sido_avg[sido] = {
            "wholesale": ws_avg,
            "retail": rt_avg,
            "retail_source": "observed" if rt_avg is not None else "unavailable",
        }

    # 전국 평균 (기준값)
    all_ws = [v for vals in sido_ws.values() for v in vals]
    national_avg_ws = round(sum(all_ws) / len(all_ws)) if all_ws else None
    all_rt = [s["retail"] for s in sido_avg.values() if s.get("retail") is not None]
    national_avg_rt = round(sum(all_rt) / len(all_rt)) if all_rt else None

    # vs_national_pct 추가 (도매 기준), retail_vs_national_pct 추가
    for s in sido_avg.values():
        if national_avg_ws:
            s["vs_national_pct"] = round((s["wholesale"] - national_avg_ws) / national_avg_ws * 100, 1)
        if national_avg_rt and s.get("retail") is not None:
            s["retail_vs_national_pct"] = round((s["retail"] - national_avg_rt) / national_avg_rt * 100, 1)

    base_date = max(r.date for r in rows)

    return {
        "item_code":      item_code,
        "base_date":      str(base_date),
        "national_avg_wholesale": national_avg_ws,
        "national_avg_retail":    national_avg_rt,
        "markets":        market_list,
        "sido_avg":       sido_avg,
    }


@router.get("/api/v1/map/weather")
async def get_map_weather(
    db: AsyncSession = Depends(get_db),
):
    """지도 날씨 레이어 — 지역별 최신 날씨"""
    from app.models.weather import DailyWeather
    from sqlalchemy import func as sqlfunc

    subq = (
        select(DailyWeather.region_code, sqlfunc.max(DailyWeather.date).label("max_date"))
        .group_by(DailyWeather.region_code)
        .subquery()
    )
    result = await db.execute(
        select(DailyWeather).join(
            subq,
            (DailyWeather.region_code == subq.c.region_code) &
            (DailyWeather.date == subq.c.max_date)
        )
    )
    rows = result.scalars().all()
    return {
        "base_date": str(max(r.date for r in rows)) if rows else None,
        "regions": [
            {
                "region_code": r.region_code,
                "region_name": r.region_name,
                "date": str(r.date),
                "avg_temp": r.avg_temp,
                "max_temp": r.max_temp,
                "min_temp": r.min_temp,
                "precipitation": r.precipitation,
                "humidity": r.humidity,
                "heat_alert": r.heat_alert,
                "cold_alert": r.cold_alert,
                "heavy_rain_alert": r.heavy_rain_alert,
                "temp_anomaly": round(r.avg_temp - r.normal_avg_temp, 1) if r.avg_temp and r.normal_avg_temp else None,
            }
            for r in rows
        ],
    }
