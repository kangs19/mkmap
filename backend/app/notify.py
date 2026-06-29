import logging
from datetime import date

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

RISK_LABEL = {
    "normal": "normal",
    "caution": "caution",
    "warning": "warning",
    "high": "high",
}

DIR_LABEL = {
    "up": "up",
    "down": "down",
    "neutral": "neutral",
    "stable": "neutral",
}


async def send_discord(content: str | None = None, embeds: list | None = None):
    """Send a Discord webhook without affecting the API when delivery fails."""
    settings = get_settings()
    if not settings.discord_webhook_url:
        return

    payload = {}
    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(settings.discord_webhook_url, json=payload)
            if response.status_code not in (200, 204):
                log.warning("Discord response status: %s", response.status_code)
    except Exception as exc:
        log.warning("Discord delivery failed: %s", exc)


async def notify_pipeline_success(results: dict):
    """Notify that the daily pipeline completed."""
    today = str(date.today())
    ok_items = [key for key, value in results.items() if value.get("status") == "ok"]
    err_items = [key for key, value in results.items() if value.get("status") != "ok"]

    fields = []
    for code, result in results.items():
        if result.get("status") != "ok":
            continue

        forecast = result.get("forecast", {})
        direction = DIR_LABEL.get(forecast.get("direction", "neutral"), "neutral")
        up_probability = forecast.get("up_probability")
        auc = forecast.get("dir_auc")

        if up_probability is None and auc is None:
            value = f"status ok | date {result.get('date', today)}"
        else:
            value = f"up probability {up_probability or 0:.0%} | AUC {auc or 0:.3f}"

        fields.append(
            {
                "name": f"{code} ({direction})",
                "value": value,
                "inline": True,
            }
        )

    color = 0x27AE60 if not err_items else 0xE67E22
    embed = {
        "title": f"Daily pipeline completed - {today}",
        "color": color,
        "fields": fields or [{"name": "result", "value": "pipeline completed", "inline": False}],
        "footer": {"text": f"success {len(ok_items)} / failed {len(err_items)}"},
    }
    if err_items:
        embed["description"] = f"Failed items: {', '.join(err_items)}"

    await send_discord(embeds=[embed])


async def notify_pipeline_error(error_msg: str, stage: str = "pipeline"):
    """Notify that a pipeline stage failed."""
    embed = {
        "title": f"{stage} error - {date.today()}",
        "description": f"```{error_msg[:1000]}```",
        "color": 0xE74C3C,
        "footer": {"text": "Check the server logs"},
    }
    await send_discord(embeds=[embed])


async def notify_sync_result(sync_result: dict):
    """Notify about data sync warnings, kept for compatibility with old callers."""
    errors = {key: value for key, value in sync_result.items() if isinstance(value, dict) and value.get("error")}
    skipped = {key: value for key, value in sync_result.items() if isinstance(value, dict) and value.get("skipped")}

    if not errors and not skipped:
        return

    lines = []
    for key, value in skipped.items():
        lines.append(f"{key}: skipped ({value.get('reason', 'no reason provided')})")
    for key, value in errors.items():
        lines.append(f"{key}: {value.get('error', 'unknown error')}")

    embed = {
        "title": f"Data sync warning - {date.today()}",
        "description": "\n".join(lines),
        "color": 0xF4B942,
    }
    await send_discord(embeds=[embed])


async def notify_daily_report(report: dict):
    """Send a compact daily risk report."""
    today = report.get("report_date", str(date.today()))
    items = report.get("items", [])

    if not items:
        return

    fields = []
    for item in items[:3]:
        risk_level = item.get("hotspot", {}).get("risk_level", "normal")
        forecast = item.get("forecast", {})
        direction = DIR_LABEL.get(forecast.get("direction_14d", "neutral"), "neutral")
        item_name = item.get("item_name") or item.get("item_code") or "item"
        summary = item.get("summary", "")[:120] or f"risk {RISK_LABEL.get(risk_level, risk_level)}, forecast {direction}"
        fields.append(
            {
                "name": f"{item_name} | {risk_level} | {direction}",
                "value": summary,
                "inline": False,
            }
        )

    embed = {
        "title": f"MK Map daily risk report - {today}",
        "color": 0x3B9AE1,
        "fields": fields,
        "footer": {"text": "mk-map.com"},
    }
    await send_discord(embeds=[embed])
