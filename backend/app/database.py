from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()


def _resolve_db_url(raw: str) -> str:
    """Railway PostgreSQL addon은 postgresql:// 형식으로 DATABASE_URL을 주입한다.
    SQLAlchemy async 드라이버는 postgresql+asyncpg:// 형식이 필요하므로 변환.
    로컬 sqlite+aiosqlite:// URL은 그대로 통과.
    """
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
