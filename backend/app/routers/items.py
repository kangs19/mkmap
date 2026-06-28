from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.database import get_db
from app.models.item import Item, ItemRegion
from app.models.price import DailyPrice
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
