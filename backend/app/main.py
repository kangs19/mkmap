from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pathlib import Path
import time, logging

from app.database import init_db
from app.routers import items, forecasts, signals, maps, admin
from app.config import get_settings
from app.scheduler import start_scheduler, stop_scheduler
from app.auth import verify_api_key, log_request

settings = get_settings()
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="AgriDigitalTwin API",
    description="농산물 가격 위험 신호 엔진 — 품목별 주산지·기상·거래량 기반 가격 방향 예측",
    version="0.2.0",
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


@app.get("/")
async def root():
    return {
        "service": "AgriDigitalTwin API",
        "version": "0.2.0",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "map_example": "/maps/items/cabbage",
    }
