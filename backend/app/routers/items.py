from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models.item import Item, ItemRegion
from app.models.price import DailyPrice
from app.models.meta import ItemMeta
from app.schemas.item import ItemListResponse, ItemResponse, ItemRegionsResponse, ItemRegionResponse
from app.utils.season import get_current_season
from datetime import date, timedelta

router = APIRouter(prefix="/api/v1/items", tags=["items"])


@router.get("", response_model=list[ItemListResponse])
async def list_items(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.is_active == True))
    items = result.scalars().all()
    return [ItemListResponse(
        item_code=i.item_code,
        item_name=i.item_name,
        category=i.category,
        available=i.is_active
    ) for i in items]


@router.get("/{item_code}", response_model=ItemResponse)
async def get_item(item_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404
        })
    return ItemResponse(
        item_code=item.item_code,
        item_name=item.item_name,
        category=item.category,
        storage_type=item.storage_type,
        price_volatility=item.price_volatility,
        import_dependency=item.import_dependency,
        weather_sensitivity=item.weather_sensitivity,
        growth_calendar=item.growth_calendar,
        demand_events=item.demand_events,
        substitute_items=item.substitute_items,
        main_markets=item.main_markets,
        metadata_confidence=item.metadata_confidence,
    )


@router.get("/{item_code}/regions", response_model=ItemRegionsResponse)
async def get_item_regions(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404
        })

    base_date = date.fromisoformat(target_date) if target_date else date.today()
    season = get_current_season(base_date.month)

    region_result = await db.execute(
        select(ItemRegion).where(
            ItemRegion.item_code == item_code,
            ItemRegion.season == season
        )
    )
    regions = region_result.scalars().all()

    return ItemRegionsResponse(
        item_code=item_code,
        item_name=item.item_name,
        base_date=str(base_date),
        season=season,
        mode="static_metadata",
        regions=[ItemRegionResponse(
            region_code=r.region_code,
            region_name=r.region_name,
            sub_regions=r.sub_regions or [],
            base_weight=r.base_weight,
            confidence=r.confidence,
            display_level="main" if r.base_weight >= 0.3 else "sub",
        ) for r in regions]
    )


@router.get("/{item_code}/price-history")
async def get_price_history(
    item_code: str,
    days: int = 90,
    db: AsyncSession = Depends(get_db)
):
    """최근 N일 가격 히스토리 (차트용)"""
    item = await db.get(Item, item_code)
    if not item:
        raise HTTPException(status_code=404, detail={"error": "item_not_found"})

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    result = await db.execute(
        select(DailyPrice).where(
            and_(
                DailyPrice.item_code == item_code,
                DailyPrice.date >= start_date,
                DailyPrice.date <= end_date,
            )
        ).order_by(DailyPrice.date)
    )
    rows = result.scalars().all()

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "unit": item.wholesale_unit,
        "days": days,
        "data": [
            {
                "date": str(r.date),
                "price": r.wholesale_price,
                "avg_year": r.avg_year_price,
                "prev_year": r.prev_year_price,
            }
            for r in rows
        ]
    }


@router.get("/{item_code}/meta")
async def get_item_meta(item_code: str, db: AsyncSession = Depends(get_db)):
    """품목별 메타데이터 — 실데이터 기반 가격/생산/기상/위험도 피처 전체"""
    meta = await db.get(ItemMeta, item_code)
    if not meta:
        raise HTTPException(status_code=404, detail={"error": "meta_not_built", "message": "메타데이터가 아직 생성되지 않았습니다. /admin/meta/build 를 먼저 실행하세요."})
    return {
        "item_code": item_code,
        "updated_at": str(meta.updated_at),
        "confidence": meta.confidence,
        "basic": {
            "name": meta.item_name, "unit": meta.unit,
            "category": meta.category_name, "main_region": meta.main_region,
            "kamis_productno": meta.kamis_productno,
        },
        "price": {
            "today":           meta.price_today,
            "avg_7d":          meta.price_avg_7d,
            "avg_30d":         meta.price_avg_30d,
            "avg_90d":         meta.price_avg_90d,
            "std_30d":         meta.price_std_30d,
            "cv_30d":          meta.price_cv_30d,
            "min_52w":         meta.price_min_52w,
            "max_52w":         meta.price_max_52w,
            "pct_of_52w_range": meta.price_pct_of_52w_range,
            "prev_year":       meta.price_prev_year,
            "yoy_change_pct":  meta.yoy_change_pct,
            "mom_7d":          meta.mom_7d,
            "mom_30d":         meta.mom_30d,
            "vs_ma30_pct":     meta.price_vs_ma30_pct,
            "trend_slope_30d": meta.trend_slope_30d,
            "seasonal_index":  meta.seasonal_index,
            "data_days":       meta.data_days_count,
            "data_from":       meta.price_data_from,
            "data_to":         meta.price_data_to,
        },
        "production": {
            "latest_year":      meta.kosis_latest_year,
            "area_ha_y1":       meta.area_ha_y1,
            "area_ha_y2":       meta.area_ha_y2,
            "area_ha_y3":       meta.area_ha_y3,
            "production_ton_y1": meta.production_ton_y1,
            "production_ton_y2": meta.production_ton_y2,
            "production_ton_y3": meta.production_ton_y3,
            "yield_per_ha_y1":  meta.yield_per_ha_y1,
            "area_yoy_pct":     meta.area_yoy_change_pct,
            "prod_yoy_pct":     meta.prod_yoy_change_pct,
        },
        "weather": {
            "region": meta.main_region,
            "temp_avg_7d":    meta.weather_temp_avg_7d,
            "precip_7d_mm":   meta.weather_precip_7d,
            "temp_anomaly_7d": meta.weather_temp_anomaly_7d,
            "stress_score":   meta.weather_stress_score,
            "alert_count_7d": meta.weather_alert_count_7d,
        },
        "risk": {
            "level":         meta.risk_level,
            "overall_score": meta.overall_risk_score,
            "price_score":   meta.price_risk_score,
            "supply_score":  meta.supply_risk_score,
            "factors":       meta.risk_factors,
        },
    }


@router.get("/meta/all")
async def get_all_meta(db: AsyncSession = Depends(get_db)):
    """전 품목 메타데이터 요약 (지도·대시보드용)"""
    result = await db.execute(select(ItemMeta).order_by(ItemMeta.item_code))
    metas = result.scalars().all()
    return [
        {
            "item_code":    m.item_code,
            "name":         m.item_name,
            "price_today":  m.price_today,
            "yoy_pct":      m.yoy_change_pct,
            "mom_7d":       m.mom_7d,
            "risk_level":   m.risk_level,
            "risk_score":   m.overall_risk_score,
            "seasonal_idx": m.seasonal_index,
            "confidence":   m.confidence,
            "updated_at":   str(m.updated_at),
        }
        for m in metas
    ]
