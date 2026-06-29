from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=(settings.app_env == "development"),
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_items()


async def _seed_items():
    """재배포 후 Item 기본 데이터 자동 삽입 (없는 경우만)"""
    from sqlalchemy import select
    from app.models.item import Item, ItemRegion

    ITEMS = [
        {"item_code": "cabbage",     "item_name": "배추", "category": "채소류", "unit": "10kg",  "is_active": True},
        {"item_code": "radish",      "item_name": "무",   "category": "채소류", "unit": "20kg",  "is_active": True},
        {"item_code": "onion",       "item_name": "양파", "category": "채소류", "unit": "20kg",  "is_active": True},
        {"item_code": "green_onion", "item_name": "대파", "category": "채소류", "unit": "1kg",   "is_active": True},
        {"item_code": "garlic",      "item_name": "마늘", "category": "채소류", "unit": "10kg",  "is_active": True},
    ]

    REGIONS = [
        # 배추
        ("cabbage", "KR-42", "강원", "고랭지", True),
        ("cabbage", "KR-46", "전남", "해남", False),
        # 무
        ("radish", "KR-46", "전남", "무안", True),
        ("radish", "KR-42", "강원", "고랭지", False),
        # 양파
        ("onion", "KR-46", "전남", "무안", True),
        ("onion", "KR-48", "경남", "창원", False),
        # 대파
        ("green_onion", "KR-46", "전남", "진도", True),
        ("green_onion", "KR-41", "경기", "수원", False),
        # 마늘
        ("garlic", "KR-47", "경북", "의성", True),
        ("garlic", "KR-46", "전남", "해남", False),
    ]

    async with AsyncSessionLocal() as db:
        for item_data in ITEMS:
            exists = await db.execute(
                select(Item).where(Item.item_code == item_data["item_code"])
            )
            if exists.scalar_one_or_none() is None:
                db.add(Item(**item_data))

        for ic, rc, rn, sub, primary in REGIONS:
            exists = await db.execute(
                select(ItemRegion).where(
                    ItemRegion.item_code == ic,
                    ItemRegion.region_code == rc,
                )
            )
            if exists.scalar_one_or_none() is None:
                db.add(ItemRegion(
                    item_code=ic,
                    region_code=rc,
                    region_name=rn,
                    sub_region=sub,
                    is_primary=primary,
                ))

        await db.commit()
