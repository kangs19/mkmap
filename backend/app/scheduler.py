from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
from pathlib import Path
import asyncio
import logging
import sys

logger = logging.getLogger("scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


async def _run_meta_pipeline_for_today() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/run_meta_pipeline.py",
        "--date",
        date.today().isoformat(),
        "--weather-lookback-days",
        "7",
        "--weather-max-requests-per-item",
        "16",
        "--weather-request-timeout-seconds",
        "8",
        cwd=str(repo_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    assert process.stdout is not None
    output_lines: list[str] = []
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip()
        output_lines.append(text)
        logger.info("[mkmap_meta] %s", text)

    return_code = await process.wait()
    if return_code != 0:
        tail = "\n".join(output_lines[-40:])
        raise RuntimeError(f"meta pipeline exited with code {return_code}: {tail}")

    return output_lines


async def daily_pipeline():
    """Run the metadata-driven daily pipeline and send the daily report."""
    from app.notify import notify_daily_report, notify_pipeline_error, notify_pipeline_success

    today = date.today()
    logger.info("[scheduler] mkmap_meta daily pipeline start: %s", today)

    try:
        output_lines = await _run_meta_pipeline_for_today()
        from app import cache

        cache.clear_prefix("signals:")
        cache.clear_prefix("report:")
        await notify_pipeline_success(
            {
                "mkmap_meta": {
                    "status": "ok",
                    "date": today.isoformat(),
                    "log_tail": output_lines[-10:],
                }
            }
        )
    except Exception as exc:
        logger.error("[scheduler] mkmap_meta pipeline error: %s", exc, exc_info=True)
        await notify_pipeline_error(str(exc), "mkmap_meta pipeline")
        return

    try:
        from app.database import AsyncSessionLocal
        from app.routers.signals import get_today_report

        async with AsyncSessionLocal() as db:
            report = await get_today_report(db)
        await notify_daily_report(report)
    except Exception as exc:
        logger.warning("[scheduler] daily report notification failed: %s", exc)


def start_scheduler():
    scheduler.add_job(
        daily_pipeline,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_pipeline",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("[scheduler] started: daily 06:00 KST")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[scheduler] stopped")
