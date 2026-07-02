from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()


def _resolve_db_url(raw: str) -> str:
    """Railway PostgreSQL addon은 postgresql:// 형식으로 DATABASE_URL을 주입한다.
    SQLAlchemy async 드라이버는 postgresql+asyncpg:// 형식이 필요하므로 변환.
    로컬 sqlite+aiosqlite:// URL은 그대로 통과.
    이미 +asyncpg 형식이면 이중 변환 방지.
    """
    if raw.startswith("postgresql+asyncpg://"):
        return raw  # 이미 올바른 형식
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw


_db_url = _resolve_db_url(settings.database_url)

engine = create_async_engine(
    _db_url,
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
        # 기존 테이블에 UniqueConstraint가 없을 경우 안전하게 추가 (PostgreSQL only)
        if _db_url.startswith("postgresql"):
            try:
                # 중복 rows 제거 (unique index 생성 전 필수)
                await conn.execute(text("""
                    DELETE FROM daily_prices a
                    USING daily_prices b
                    WHERE a.id > b.id
                      AND a.item_code = b.item_code
                      AND a.date = b.date
                      AND a.source = b.source
                """))
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_prices_item_date_source "
                        "ON daily_prices (item_code, date, source)"
                    )
                )
                await conn.execute(text("""
                    DELETE FROM daily_market a
                    USING daily_market b
                    WHERE a.id > b.id
                      AND a.item_code = b.item_code
                      AND a.date = b.date
                      AND a.source = b.source
                """))
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_market_item_date_source "
                        "ON daily_market (item_code, date, source)"
                    )
                )
                await conn.execute(text("""
                    DELETE FROM daily_weather a
                    USING daily_weather b
                    WHERE a.id > b.id
                      AND a.region_code = b.region_code
                      AND a.date = b.date
                      AND a.source = b.source
                """))
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_weather_region_date_source "
                        "ON daily_weather (region_code, date, source)"
                    )
                )
                await conn.execute(text("""
                    DELETE FROM forecasts a
                    USING forecasts b
                    WHERE a.id > b.id
                      AND a.item_code = b.item_code
                      AND a.base_date = b.base_date
                """))
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_forecasts_item_date "
                        "ON forecasts (item_code, base_date)"
                    )
                )
            except Exception:
                pass  # 이미 존재하거나 다른 이유로 실패해도 무시
