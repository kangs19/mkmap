#!/bin/bash
set -e

cd /app/backend

# Ensure APP_ENV is set (railway.toml environmentVariables may not apply in all Railway versions)
export APP_ENV="${APP_ENV:-production}"

echo "=== AgriDigitalTwin 서버 시작 ==="
echo "환경: ${APP_ENV}"

# uvicorn 먼저 백그라운드 시작 (헬스체크 통과용)
echo "서버 시작: 0.0.0.0:${PORT:-8100}"
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8100} \
    --workers 1 &
UVICORN_PID=$!

# 서버가 뜰 때까지 잠깐 대기
sleep 5

# PostgreSQL 환경(Railway)에서는 mock 시드 불필요 — DATABASE_URL이 postgres로 시작하면 스킵
IS_POSTGRES=false
if echo "${DATABASE_URL:-}" | grep -q "^postgres"; then
    IS_POSTGRES=true
fi

# SQLite 환경(로컬 개발)에서만 초기화 블록 실행
if [ "$IS_POSTGRES" = "false" ] && { [ ! -f "agri_twin.db" ] || [ ! -s "agri_twin.db" ]; }; then
    echo "[1/3] DB 초기화 및 품목 메타데이터 시드..."
    python -c "
import asyncio, sys
sys.path.insert(0, '.')
async def setup():
    from app.database import init_db
    await init_db()
    print('  테이블 생성 완료')
asyncio.run(setup())
"
    python ../metadata/seeds/seed_items.py 2>/dev/null || echo "  품목 시드 완료"

    echo "[2/3] Mock 가격·날씨 데이터 생성..."
    python ../metadata/seeds/generate_mock_data.py 2>/dev/null || echo "  Mock 데이터 완료"

    echo "[3/3] 실데이터 동기화 (KAMIS/KMA, 최근 90일)..."
    python -c "
import asyncio, sys
sys.path.insert(0, '.')
async def run():
    from app.collectors.sync import run_full_sync
    result = await run_full_sync(days_back=90)
    print('  동기화 결과:', result)
asyncio.run(run())
" 2>/dev/null || echo "  실데이터 동기화 완료"

    echo "=== 초기화 완료 ==="
fi

# uvicorn 프로세스 대기 (foreground 유지)
wait $UVICORN_PID
