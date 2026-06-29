from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import time, logging

from app.database import init_db
from app.models import (  # noqa: F401 — Base.metadata.create_all 위해 모두 로드
    Item, ItemRegion, ItemEvent, DailyPrice, DailyWeather, DailyMarket,
    RegionSignal, Forecast, ApiKey, ApiUsage, CropProduction, ItemMeta,
)
from app.routers import items, forecasts, signals, maps, admin
from app.config import get_settings
from app.scheduler import start_scheduler, stop_scheduler
from app.auth import verify_api_key, log_request

settings = get_settings()
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _seed_items()
    start_scheduler()
    yield
    stop_scheduler()


async def _seed_items():
    """재배포 후 Item 기본 데이터 자동 삽입 (없는 경우만)"""
    import logging
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.item import Item, ItemRegion

    ITEMS = [
        {"item_code": "cabbage",     "item_name": "배추", "category": "채소류", "wholesale_unit": "10kg",  "is_active": True},
        {"item_code": "radish",      "item_name": "무",   "category": "채소류", "wholesale_unit": "20kg",  "is_active": True},
        {"item_code": "onion",       "item_name": "양파", "category": "채소류", "wholesale_unit": "20kg",  "is_active": True},
        {"item_code": "green_onion", "item_name": "대파", "category": "채소류", "wholesale_unit": "1kg",   "is_active": True},
        {"item_code": "garlic",      "item_name": "마늘", "category": "채소류", "wholesale_unit": "10kg",  "is_active": True},
    ]
    REGIONS = [
        ("cabbage",     "KR-46", "전남", "해남",   True),
        ("cabbage",     "KR-42", "강원", "고랭지",  False),
        ("radish",      "KR-46", "전남", "무안",   True),
        ("radish",      "KR-42", "강원", "고랭지",  False),
        ("onion",       "KR-46", "전남", "무안",   True),
        ("onion",       "KR-48", "경남", "창원",   False),
        ("green_onion", "KR-46", "전남", "진도",   True),
        ("green_onion", "KR-41", "경기", "수원",   False),
        ("garlic",      "KR-47", "경북", "의성",   True),
        ("garlic",      "KR-46", "전남", "해남",   False),
    ]

    try:
        async with AsyncSessionLocal() as db:
            for item_data in ITEMS:
                existing = await db.execute(
                    select(Item).where(Item.item_code == item_data["item_code"])
                )
                if existing.scalar_one_or_none() is None:
                    db.add(Item(**item_data))

            for ic, rc, rn, sub, primary in REGIONS:
                existing = await db.execute(
                    select(ItemRegion).where(
                        ItemRegion.item_code == ic,
                        ItemRegion.region_code == rc,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    db.add(ItemRegion(
                        item_code=ic, region_code=rc,
                        region_name=rn, sub_region=sub, is_primary=primary,
                    ))

            await db.commit()
            logging.info("[seed] Item 시드 완료")
    except Exception as e:
        logging.error(f"[seed] 실패: {e}")


app = FastAPI(
    title="AgriDigitalTwin API",
    description="농산물 가격 위험 신호 엔진 — 품목별 주산지·기상·거래량 기반 가격 방향 예측",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "X-API-Key", "X-Admin-Key"],
)

static_path = Path(__file__).parent.parent.parent / "map_viewer" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.middleware("http")
async def auth_and_log(request: Request, call_next):
    start = time.time()

    # API 키 검증
    try:
        key_hash = await verify_api_key(request)
    except Exception as e:
        from fastapi.responses import JSONResponse as JR
        from fastapi import HTTPException
        if isinstance(e, HTTPException):
            return JR(status_code=e.status_code, content=e.detail)
        return JR(status_code=500, content={"error": "internal_error"})

    response = await call_next(request)

    latency = int((time.time() - start) * 1000)
    response.headers["X-Response-Time"] = f"{latency}ms"

    # 사용량 비동기 로그 (API 경로만)
    if request.url.path.startswith("/api/"):
        import asyncio
        asyncio.create_task(log_request(
            key_hash, request.url.path,
            request.method, response.status_code, latency
        ))

    return response


app.include_router(items.router)
app.include_router(forecasts.router)
app.include_router(signals.router)
app.include_router(maps.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    from app.scheduler import scheduler
    return {
        "status": "ok",
        "version": "0.2.0",
        "env": settings.app_env,
        "scheduler": scheduler.running,
    }


@app.get("/map_standalone.html")
async def map_standalone():
    p = Path(__file__).parent.parent.parent / "map_standalone.html"
    return FileResponse(str(p), media_type="text/html")


@app.get("/index.html")
async def index_html():
    p = Path(__file__).parent.parent.parent / "index.html"
    return FileResponse(str(p), media_type="text/html")


@app.get("/")
async def root():
    p = Path(__file__).parent.parent.parent / "index.html"
    return FileResponse(str(p), media_type="text/html")
