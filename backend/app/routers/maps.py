from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter(tags=["maps"])

TEMPLATES = Path(__file__).parent.parent.parent.parent / "map_viewer" / "templates"
TEMPLATE_PATH = TEMPLATES / "item_map.html"
DASHBOARD_PATH = TEMPLATES / "dashboard.html"
WIDGET_PATH    = TEMPLATES / "widget.html"

ITEM_NAMES = {
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "green_onion": "대파",
    "garlic": "마늘",
}


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


@router.get("/widget", response_class=HTMLResponse)
async def get_widget(request: Request):
    """WordPress iframe 임베드용 위젯"""
    html = WIDGET_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html)
