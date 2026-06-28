"""
메타데이터 YAML → DB 시드 스크립트
실행: python metadata/seeds/seed_items.py
"""
import asyncio
import yaml
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.database import AsyncSessionLocal, init_db
from app.models.item import Item, ItemRegion, ItemEvent


SEASON_MAP = {"spring": "spring", "summer": "summer", "autumn": "autumn", "winter": "winter"}


async def seed_item(yaml_path: Path, session):
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    item_code = data["item_code"]

    existing = await session.get(Item, item_code)
    if existing:
        print(f"  이미 존재: {item_code} — 업데이트")
        item = existing
    else:
        item = Item(item_code=item_code)
        session.add(item)

    pc = data.get("price_character", {})
    item.item_name = data["item_name"]
    item.category = data["category"]
    item.wholesale_unit = data.get("units", {}).get("wholesale", "")
    item.retail_unit = data.get("units", {}).get("retail", "")
    item.storage_type = data.get("storage", {}).get("type", "")
    item.price_volatility = pc.get("volatility", "")
    item.import_dependency = pc.get("import_dependency", "")
    item.weather_sensitivity = data.get("weather_sensitivity", {})
    item.growth_calendar = data.get("growth_calendar", {})
    item.demand_events = data.get("demand_events", [])
    item.substitute_items = data.get("substitute_items", [])
    item.main_markets = data.get("main_markets", [])
    item.metadata_confidence = data.get("metadata_quality", {}).get("confidence", "draft")

    await session.flush()

    # 기존 지역 삭제 후 재삽입
    from sqlalchemy import delete
    await session.execute(delete(ItemRegion).where(ItemRegion.item_code == item_code))
    await session.execute(delete(ItemEvent).where(ItemEvent.item_code == item_code))

    for season, season_data in data.get("production_regions", {}).items():
        for r in season_data.get("regions", []):
            # source 필드는 중첩 또는 직접 필드 둘 다 지원
            src = r.get("source", {})
            region = ItemRegion(
                item_code=item_code,
                season=season,
                season_description=season_data.get("description", ""),
                region_code=r["region_code"],
                region_name=r["region_name"],
                sub_regions=r.get("sub_regions", []),
                base_weight=r["base_weight"],
                confidence=r.get("confidence", "draft"),
                source_type=r.get("source_type", src.get("type", "manual_research")),
                source_name=r.get("source_name", src.get("name", "")),
                source_note=r.get("source_note", src.get("note", "")),
                center_lat=r.get("center_lat"),
                center_lng=r.get("center_lng"),
            )
            session.add(region)

    for ev in data.get("demand_events", []):
        event = ItemEvent(
            item_code=item_code,
            event_name=ev.get("name", ev.get("event_name", "")),
            event_months=ev.get("months"),
            effect=ev.get("effect", ""),
            importance=ev.get("importance", "medium"),
        )
        session.add(event)

    print(f"  완료: {item_code} ({data['item_name']})")


async def main():
    print("DB 초기화...")
    await init_db()

    items_dir = Path(__file__).parent.parent / "items"
    yaml_files = list(items_dir.glob("*.yaml"))
    print(f"발견된 YAML 파일: {len(yaml_files)}개")

    async with AsyncSessionLocal() as session:
        for yaml_path in sorted(yaml_files):
            print(f"\n처리 중: {yaml_path.name}")
            await seed_item(yaml_path, session)
        await session.commit()

    print("\n✅ 시드 완료")


if __name__ == "__main__":
    asyncio.run(main())
