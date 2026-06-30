"""
API Smoke Test — 기획서 20번
pytest로 실행: cd backend && pytest tests/ -v
"""
import pytest
import os
from datetime import date
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app.database import AsyncSessionLocal, init_db
from app.main import app
from app.models.forecast import Forecast
from app.models.item import Item
from app.models.price import DailyPrice
from app.models.signal import RegionSignal


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
async def test_forecast_explanation_endpoint(client, item_code):
    r = await client.get(f"/api/v1/items/{item_code}/forecast/explanation")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert "headline" in data
        assert "model" in data
        assert "confidence_reason" in data["model"]
        assert "confidence_factors" in data["model"]
        assert "data_freshness" in data


@pytest.mark.asyncio
async def test_forecast_explanation_payload(client):
    item_code = "test_explain_crop"
    base_date = date(2026, 1, 15)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(DailyPrice).where(DailyPrice.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="테스트품목",
            category="테스트",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="price_baseline_v1_global",
            direction_14d="up",
            up_probability_14d=0.64,
            surge_probability_14d=0.18,
            volatility_risk_30d="medium",
            bottom_probability=0.36,
            top_factors=[
                {"factor": "price_lag_model", "contribution": 0.02, "direction": "up"},
                {"factor": "risk_overlay", "contribution": 0.01, "direction": "up"},
            ],
            national_supply_shock=0.01,
            confidence="medium",
        ))
        db.add(DailyPrice(
            item_code=item_code,
            date=base_date,
            market="test",
            grade="test",
            wholesale_price=1000,
            retail_price=1200,
            avg_year_price=1100,
            prev_year_price=1050,
            source="test",
        ))
        db.add(RegionSignal(
            item_code=item_code,
            region_code="TEST-1",
            region_name="테스트지역",
            date=base_date,
            risk_score=72.5,
            risk_level="warning",
            supply_shock=0.2,
            price_effect="up",
            weather_summary={},
            market_summary={},
            summary_text="테스트 위험 신호",
        ))
        await db.commit()

    r = await client.get(f"/api/v1/items/{item_code}/forecast/explanation?target_date={base_date}")
    assert r.status_code == 200
    data = r.json()
    assert data["headline"]
    assert data["model"]["scope"] == "global"
    assert data["model"]["confidence_reason"]
    assert any(factor["key"] == "price_freshness" for factor in data["model"]["confidence_factors"])
    assert data["forecast"]["direction_label"] == "상승"
    assert data["data_freshness"]["price"]["status"] == "fresh"
    assert data["risk_regions"][0]["region_name"] == "테스트지역"


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
async def test_forecast_explanation_page(client):
    r = await client.get("/forecast-explanation")
    assert r.status_code == 200
    assert "forecast-explanation-root" in r.text
    assert "/api/v1/items/" in r.text


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
        assert "daily_weather" in data["data_freshness"]
        assert "status" in data["data_freshness"]["daily_weather"]
        assert "api_diagnostics" in data
        assert "status" in data["api_diagnostics"]
