"""
일별 자동 파이프라인 스케줄러
매일 06:00 가격예측 + 지역위험도 자동 계산
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
import logging

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


async def daily_pipeline():
    """매일 06:00 실행 — 실데이터 동기화 → 예측 → 위험 신호 → Discord 알림"""
    from app.notify import notify_sync_result, notify_pipeline_success, notify_pipeline_error, notify_daily_report

    logger.info(f"[scheduler] 일별 파이프라인 시작: {date.today()}")

    # 1. 실데이터 수집
    sync_result = {}
    try:
        from app.collectors.sync import daily_sync
        sync_result = await daily_sync()
        logger.info(f"[scheduler] 실데이터 동기화: {sync_result}")
        await notify_sync_result(sync_result)
    except Exception as e:
        logger.warning(f"[scheduler] 실데이터 동기화 실패 (mock으로 계속): {e}")
        await notify_pipeline_error(str(e), "데이터 수집")

    # 2. 예측 파이프라인
    try:
        from app.pipeline.batch import run_batch
        results = await run_batch(verbose=False)
        ok = sum(1 for v in results.values() if v.get("status") == "ok")
        logger.info(f"[scheduler] 완료: {ok}/{len(results)}개 품목 성공")
        from app import cache
        cache.clear_prefix("signals:")
        cache.clear_prefix("report:")
        await notify_pipeline_success(results)
    except Exception as e:
        logger.error(f"[scheduler] 파이프라인 오류: {e}", exc_info=True)
        await notify_pipeline_error(str(e), "예측 파이프라인")
        return

    # 3. 일일 리포트 Discord 알림
    try:
        from app.routers.signals import get_today_report
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            report = await get_today_report(db)
        await notify_daily_report(report)
    except Exception as e:
        logger.warning(f"[scheduler] 리포트 알림 실패: {e}")


def start_scheduler():
    scheduler.add_job(
        daily_pipeline,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_pipeline",
        replace_existing=True,
        misfire_grace_time=3600,   # 1시간 내 놓친 실행 허용
    )
    scheduler.start()
    logger.info("[scheduler] 스케줄러 시작 — 매일 06:00 KST 실행")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] 스케줄러 종료")
