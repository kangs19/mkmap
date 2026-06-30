from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from sqlalchemy import select, and_
from pathlib import Path
from datetime import date

from app.database import get_db
from app.models.signal import RegionSignal
from app.models.price import DailyPrice
from app.models.production import CropProduction

router = APIRouter(tags=["maps"])

TEMPLATES = Path(__file__).parent.parent.parent.parent / "map_viewer" / "templates"
TEMPLATE_PATH = TEMPLATES / "item_map.html"
DASHBOARD_PATH = TEMPLATES / "dashboard.html"
WIDGET_PATH    = TEMPLATES / "widget.html"
ADMIN_PATH     = TEMPLATES / "admin.html"
FORECAST_EXPLANATION_PATH = TEMPLATES / "forecast_explanation.html"

ITEM_NAMES = {
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "green_onion": "대파",
    "garlic": "마늘",
}


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


@router.get("/api/v1/map/signals")
async def get_map_signals(
    item_code: str = "cabbage",
    target_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    """지도용 — 품목별 전국 지역 위험 신호 (Leaflet 직접 소비)"""
    base_date = date.fromisoformat(target_date) if target_date else date.today()

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
    end = date.today()
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
    """지도용 — KOSIS 연간 재배면적·생산량"""
    result = await db.execute(
        select(CropProduction)
        .where(CropProduction.item_code == item_code)
        .order_by(CropProduction.year.desc())
        .limit(5)
    )
    rows = result.scalars().all()
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
