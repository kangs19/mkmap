"""
API Smoke Test — 기획서 20번
pytest로 실행: cd backend && pytest tests/ -v
"""
import pytest
import os
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from app import cache
from app.database import AsyncSessionLocal, init_db
from app.main import app
from app.timezone import kst_today
from app.models.forecast import Forecast
from app.models.item import Item
from app.models.price import DailyPrice
from app.models.regional_price import RegionalMarketPrice
from app.models.signal import RegionSignal
from app.models.farmmap import FarmMapLanduseRegion


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
async def test_auth_error_messages_are_public_korean(client):
    login = await client.post("/api/v1/auth/login", json={
        "email": "missing-auth-qa@example.com",
        "password": "wrong-password",
    })
    assert login.status_code == 401
    assert login.json()["detail"]["message"] == "이메일 또는 비밀번호가 올바르지 않습니다."

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401
    assert me.json()["detail"]["message"] == "로그인이 필요합니다."

    farmer = await client.post("/api/v1/auth/register", json={
        "email": "farmer-no-phone-auth-qa@example.com",
        "password": "12345678",
        "nickname": "농가QA",
        "role": "farmer",
        "terms_accepted": True,
    })
    assert farmer.status_code == 400
    assert farmer.json()["detail"]["error"] == "phone_required"
    assert farmer.json()["detail"]["message"] == "농부·유통인 회원은 휴대폰 인증이 필요합니다."

    phone = await client.post("/api/v1/auth/phone/send", json={"phone": "123"})
    assert phone.status_code == 400
    assert phone.json()["detail"]["message"] == "올바른 휴대폰 번호를 입력해 주세요."

    verify = await client.post("/api/v1/auth/phone/verify", json={"phone": "123", "code": "12ab"})
    assert verify.status_code == 400
    assert verify.json()["detail"]["message"] == "올바른 휴대폰 번호를 입력해 주세요."


@pytest.mark.asyncio
async def test_signals_today_uses_latest_forecast_when_today_is_empty(client):
    item_code = "test_latest_signal_crop"
    base_date = kst_today() - timedelta(days=1)
    cache.delete("signals:today")
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.date == kst_today()))
        await db.execute(delete(Forecast).where(Forecast.base_date == kst_today()))
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="latest signal crop",
            category="test",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="test_latest_forecast",
            horizon_days=14,
            direction_14d="up",
            up_probability_14d=0.72,
            surge_probability_14d=0.2,
            volatility_risk_30d="high",
            confidence="medium",
        ))
        await db.commit()

    r = await client.get("/api/v1/signals/today")
    assert r.status_code == 200
    data = r.json()
    assert data["base_date"] == str(base_date)
    item = next(x for x in data["items"] if x["item_code"] == item_code)
    assert item["direction_14d"] == "up"
    assert item["up_probability_14d"] == 0.72
    assert item["risk_level"] == "high"


@pytest.mark.asyncio
async def test_public_signal_region_names_prefer_canonical_kr_code(client):
    item_code = "test_public_region_name_crop"
    base_date = kst_today()
    cache.delete("signals:today")
    cache.delete("report:today")
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="public region name crop",
            category="test",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="test_public_region_name",
            horizon_days=14,
            direction_14d="up",
            up_probability_14d=0.77,
            surge_probability_14d=0.21,
            volatility_risk_30d="high",
            confidence="medium",
        ))
        db.add(RegionSignal(
            item_code=item_code,
            region_code="KR-46",
            region_name="?꾨씪?⑤룄",
            date=base_date,
            risk_score=91.0,
            risk_level="high",
            supply_shock=0.2,
            price_effect="up",
            weather_summary={},
            market_summary={},
            summary_text="test summary",
        ))
        await db.commit()

    today = await client.get("/api/v1/signals/today")
    assert today.status_code == 200
    item = next(x for x in today.json()["items"] if x["item_code"] == item_code)
    assert item["hotspot_region"] == "전남"

    cards = await client.get(f"/api/v1/dashboard/cards?target_date={base_date}&limit=50")
    assert cards.status_code == 200
    card = next(x for x in cards.json()["cards"] if x["item_code"] == item_code)
    assert card["risk"]["hotspot_region"] == "전남"

    alerts = await client.get(f"/api/v1/alerts/high-risk?target_date={base_date}&min_risk_score=70&min_up_probability=0.6")
    assert alerts.status_code == 200
    alert = next(x for x in alerts.json()["alerts"] if x["item_code"] == item_code)
    assert alert["region_name"] == "전남"


@pytest.mark.asyncio
async def test_regional_price_endpoint_normalizes_garlic_unit_outlier(client):
    item_code = "garlic"
    base_date = date(2026, 7, 3)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionalMarketPrice).where(RegionalMarketPrice.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="garlic",
            category="test",
            wholesale_unit="20kg",
            is_active=True,
        ))
        db.add_all([
            RegionalMarketPrice(item_code=item_code, date=base_date, market_code="T001", market_name="Seoul", sido="Seoul", wholesale_price=4000, retail_price=5400),
            RegionalMarketPrice(item_code=item_code, date=base_date, market_code="T002", market_name="Busan", sido="Busan", wholesale_price=4200, retail_price=5600),
            RegionalMarketPrice(item_code=item_code, date=base_date, market_code="T003", market_name="Daegu", sido="Daegu", wholesale_price=3900, retail_price=5200),
            RegionalMarketPrice(item_code=item_code, date=base_date, market_code="T004", market_name="Jeju", sido="Jeju", wholesale_price=153613, retail_price=207378),
        ])
        await db.commit()

    r = await client.get(f"/api/v1/map/regional-prices?item_code={item_code}")
    assert r.status_code == 200
    data = r.json()
    jeju = data["sido_avg"]["Jeju"]
    assert jeju["wholesale"] == 7681
    assert jeju["wholesale_quality"] == "unit_adjusted"
    assert jeju["retail"] == 10369
    assert jeju["retail_quality"] == "unit_adjusted"
    assert data["national_avg_wholesale"] < 6000


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
        assert "pressure_summary" in data
        assert "reason_groups" in data


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
    assert data["direction"] == "up"
    assert data["up_probability_14d"] == 0.64
    assert data["pressure_summary"]["direction"] == "up"
    assert data["pressure_summary"]["up_count"] >= 2
    assert any(group["direction"] == "up" for group in data["reason_groups"])
    assert data["data_freshness"]["price"]["status"] == "fresh"
    assert data["risk_regions"][0]["region_name"] == "테스트지역"


@pytest.mark.asyncio
async def test_forecast_public_payload_hides_internal_column_factors(client):
    item_code = "test_column_factor_crop"
    base_date = date(2026, 3, 5)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(DailyPrice).where(DailyPrice.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="테스트작물",
            category="test",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="lgbm_ensemble_test",
            horizon_days=14,
            direction_14d="up",
            up_probability_14d=0.66,
            surge_probability_14d=0.11,
            volatility_risk_30d="medium",
            bottom_probability=0.34,
            top_factors=[
                {"factor": "Column_17", "contribution": 0.88, "direction": "up"},
                {"factor": "Column_10", "contribution": 0.42, "direction": "down"},
            ],
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
        await db.commit()

    forecast = await client.get(f"/api/v1/items/{item_code}/forecast?target_date={base_date}")
    assert forecast.status_code == 200
    factor_names = [factor["factor"] for factor in forecast.json()["top_factors"]]
    assert "Column_17" not in factor_names
    assert "공급·출하 압력" in factor_names

    explanation = await client.get(f"/api/v1/items/{item_code}/forecast/explanation?target_date={base_date}")
    assert explanation.status_code == 200
    reason_labels = [reason["label"] for reason in explanation.json()["reasons"]]
    reason_messages = [reason.get("message", "") for reason in explanation.json()["reasons"]]
    assert "Column_17" not in reason_labels
    assert "공급·출하 압력" in reason_labels
    assert any("가격을 올리거나 흔드는 쪽" in message for message in reason_messages)


@pytest.mark.asyncio
async def test_dashboard_cards_payload(client):
    item_code = "test_card_crop"
    base_date = date(2026, 2, 10)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(DailyPrice).where(DailyPrice.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="테스트카드품목",
            category="테스트",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="price_baseline_v1_item",
            direction_14d="up",
            up_probability_14d=0.71,
            surge_probability_14d=0.22,
            volatility_risk_30d="medium",
            bottom_probability=0.29,
            top_factors=[{"factor": "price_lag_model", "contribution": 0.02, "direction": "up"}],
            national_supply_shock=0.02,
            confidence="high",
        ))
        db.add(DailyPrice(
            item_code=item_code,
            date=date(2026, 1, 20),
            market="test",
            grade="test",
            wholesale_price=1000,
            retail_price=1200,
            avg_year_price=1100,
            prev_year_price=1050,
            source="test",
        ))
        db.add(DailyPrice(
            item_code=item_code,
            date=base_date,
            market="test",
            grade="test",
            wholesale_price=1150,
            retail_price=1300,
            avg_year_price=1120,
            prev_year_price=1060,
            source="test",
        ))
        db.add(RegionSignal(
            item_code=item_code,
            region_code="TEST-CARD",
            region_name="카드지역",
            date=base_date,
            risk_score=81.0,
            risk_level="warning",
            supply_shock=0.25,
            price_effect="up",
            weather_summary={},
            market_summary={},
            summary_text="카드 위험 신호",
        ))
        await db.commit()

    r = await client.get(f"/api/v1/dashboard/cards?target_date={base_date}&limit=5")
    assert r.status_code == 200
    data = r.json()
    card = next(card for card in data["cards"] if card["item_code"] == item_code)
    assert card["item_name"] == "테스트카드품목"
    assert card["forecast"]["model_scope"] == "item"
    assert card["risk"]["hotspot_region"] == "카드지역"
    assert card["price"]["change_30d_pct"] == 15.0


@pytest.mark.asyncio
async def test_high_risk_alerts_payload(client):
    item_code = "test_alert_crop"
    base_date = date(2026, 2, 11)
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RegionSignal).where(RegionSignal.item_code == item_code))
        await db.execute(delete(Forecast).where(Forecast.item_code == item_code))
        await db.execute(delete(Item).where(Item.item_code == item_code))
        db.add(Item(
            item_code=item_code,
            item_name="테스트알림품목",
            category="테스트",
            wholesale_unit="1kg",
            is_active=True,
        ))
        db.add(Forecast(
            item_code=item_code,
            base_date=base_date,
            model_version="price_baseline_v1_global",
            direction_14d="up",
            up_probability_14d=0.76,
            surge_probability_14d=0.31,
            volatility_risk_30d="high",
            bottom_probability=0.24,
            top_factors=[],
            national_supply_shock=0.03,
            confidence="medium",
        ))
        db.add(RegionSignal(
            item_code=item_code,
            region_code="TEST-ALERT",
            region_name="알림지역",
            date=base_date,
            risk_score=88.0,
            risk_level="high",
            supply_shock=0.35,
            price_effect="up",
            weather_summary={},
            market_summary={},
            summary_text="고위험 알림 신호",
        ))
        await db.commit()

    r = await client.get(f"/api/v1/alerts/high-risk?target_date={base_date}&min_risk_score=70&min_up_probability=0.6")
    assert r.status_code == 200
    data = r.json()
    alert = next(alert for alert in data["alerts"] if alert["item_code"] == item_code)
    assert alert["severity"] == "critical"
    assert "risk_score" in alert["triggered_rules"]
    assert "up_probability" in alert["triggered_rules"]
    assert alert["region_name"] == "알림지역"


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
async def test_farmmap_crop_regions_contract(client):
    r = await client.get("/api/v1/map/farmmap/crop-regions?item_code=cabbage")
    assert r.status_code == 200
    data = r.json()
    assert data["item_code"] == "cabbage"
    assert data["source"] == "farmmap"
    assert "available" in data
    assert "regions" in data


@pytest.mark.asyncio
async def test_farmmap_landuse_regions_contract(client):
    source_file = "test_farmmap_landuse.json"
    async with AsyncSessionLocal() as db:
        await db.execute(delete(FarmMapLanduseRegion).where(FarmMapLanduseRegion.source_file == source_file))
        db.add(FarmMapLanduseRegion(
            sido="제주특별자치도",
            sigungu="제주시",
            landuse_class="밭",
            parcel_count=12,
            area_m2=345000.0,
            area_ha=34.5,
            source_file=source_file,
            source="farmmap",
            confidence="landuse_only",
        ))
        await db.commit()

    r = await client.get("/api/v1/map/farmmap/landuse-regions?sido=제주특별자치도")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["source"] == "farmmap"
    assert data["source_type"] == "landuse_only"
    assert data["total_area_ha"] >= 34.5
    assert data["class_totals_ha"]["밭"] >= 34.5
    assert any(row["source_file"] == source_file for row in data["regions"])


@pytest.mark.asyncio
async def test_farmmap_crop_capacity_contract(client):
    source_file = "test_farmmap_capacity.json"
    async with AsyncSessionLocal() as db:
        await db.execute(delete(FarmMapLanduseRegion).where(FarmMapLanduseRegion.source_file == source_file))
        db.add_all([
            FarmMapLanduseRegion(
                sido="강원특별자치도",
                sigungu="평창군",
                landuse_class="밭",
                parcel_count=120,
                area_m2=1_500_000.0,
                area_ha=150.0,
                source_file=source_file,
                source="farmmap",
                confidence="landuse_only",
            ),
            FarmMapLanduseRegion(
                sido="강원특별자치도",
                sigungu="평창군",
                landuse_class="논",
                parcel_count=40,
                area_m2=400_000.0,
                area_ha=40.0,
                source_file=source_file,
                source="farmmap",
                confidence="landuse_only",
            ),
        ])
        await db.commit()

    r = await client.get("/api/v1/map/farmmap/crop-capacity?item_code=cabbage")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["source_type"] == "crop_metadata_plus_farmmap_landuse"
    region = next(row for row in data["regions"] if row["region_code"] == "32340")
    assert region["region_name"] == "평창군"
    assert region["farmmap_match_level"] == "sigungu"
    assert region["confidence"] == "high"
    assert region["farmmap_landuse"]["agri_area_ha"] >= 190
    assert region["capacity_score"] is not None
    assert "not FarmMap crop acreage" in data["score_meaning"]


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
