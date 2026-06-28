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
    """매일 06:00 실행 — 전 품목 예측 + 위험 신호"""
    logger.info(f"[scheduler] 일별 파이프라인 시작: {date.today()}")
    try:
        from app.pipeline.batch import run_batch
        results = await run_batch(verbose=False)
        ok = sum(1 for v in results.values() if v.get("status") == "ok")
        logger.info(f"[scheduler] 완료: {ok}/{len(results)}개 품목 성공")
    except Exception as e:
        logger.error(f"[scheduler] 파이프라인 오류: {e}", exc_info=True)


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
