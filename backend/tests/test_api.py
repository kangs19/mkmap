"""
API Smoke Test — 기획서 20번
pytest로 실행: cd backend && pytest tests/ -v
"""
import pytest
import os
from httpx import AsyncClient, ASGITransport
from app.database import init_db
from app.main import app


@pytest.fixture
async def client():
    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_signals_today(client):
    r = await client.get("/api/v1/signals/today")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "base_date" in data


@pytest.mark.asyncio
@pytest.mark.parametrize("item_code", ["cabbage", "radish", "onion", "green_onion", "garlic"])
async def test_forecast_endpoint(client, item_code):
    r = await client.get(f"/api/v1/items/{item_code}/forecast")
    # 404는 데이터 없는 것(정상), 500은 서버 오류(비정상)
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
@pytest.mark.parametrize("item_code", ["cabbage", "radish", "onion", "green_onion", "garlic"])
async def test_map_signals(client, item_code):
    r = await client.get(f"/api/v1/map/signals?item_code={item_code}")
    assert r.status_code == 200
    data = r.json()
    assert "regions" in data
    assert data["item_code"] == item_code


@pytest.mark.asyncio
@pytest.mark.parametrize("item_code", ["cabbage", "radish", "onion", "green_onion", "garlic"])
async def test_map_prices(client, item_code):
    r = await client.get(f"/api/v1/map/prices?item_code={item_code}")
    assert r.status_code == 200
    assert "prices" in r.json()


@pytest.mark.asyncio
async def test_report_today(client):
    r = await client.get("/api/v1/report/today")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert "report_date" in data


@pytest.mark.asyncio
async def test_widget(client):
    r = await client.get("/widget")
    assert r.status_code == 200
    assert "농산물" in r.text


@pytest.mark.asyncio
async def test_widget_embed_guide(client):
    r = await client.get("/widget/embed")
    assert r.status_code == 200
    assert "iframe" in r.text


@pytest.mark.asyncio
async def test_admin_status(client):
    admin_key = os.environ.get("ADMIN_KEY", "dev-admin-key")
    r = await client.get("/api/v1/admin/status",
                         headers={"X-Admin-Key": admin_key})
    assert r.status_code in (200, 403, 503)
    if r.status_code == 200:
        data = r.json()
        assert "data_freshness" in data
        assert "forecasts" in data["data_freshness"]
