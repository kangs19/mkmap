"""
Discord Webhook 알림 — 기획서 21번

스케줄러 성공/실패, 데이터 수집 오류, 파이프라인 이상을 Discord로 전송
"""
import httpx
import asyncio
import logging
from datetime import date
from app.config import get_settings

log = logging.getLogger(__name__)

RISK_EMOJI = {"normal": "🟢", "caution": "🟡", "warning": "🟠", "high": "🔴"}
DIR_EMOJI  = {"up": "📈", "down": "📉", "neutral": "➡️"}


async def send_discord(content: str = None, embeds: list = None):
    """Discord Webhook 전송 (실패해도 서비스에 영향 없음)"""
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
            r = await client.post(settings.discord_webhook_url, json=payload)
            if r.status_code not in (200, 204):
                log.warning(f"Discord 응답 {r.status_code}")
    except Exception as e:
        log.warning(f"Discord 전송 실패: {e}")


async def notify_pipeline_success(results: dict):
    """파이프라인 정상 완료 알림"""
    today = str(date.today())
    ok_items = [k for k, v in results.items() if v.get("status") == "ok"]
    err_items = [k for k, v in results.items() if v.get("status") != "ok"]

    item_name = {"cabbage": "배추", "radish": "무", "onion": "양파",
                 "green_onion": "대파", "garlic": "마늘"}

    fields = []
    for code, r in results.items():
        if r.get("status") != "ok":
            continue
        fc = r.get("forecast", {})
        dir_e = DIR_EMOJI.get(fc.get("direction", "neutral"), "➡️")
        fields.append({
            "name": f"{dir_e} {item_name.get(code, code)}",
            "value": f"상승확률 {fc.get('up_probability', 0):.0%} | AUC {fc.get('dir_auc', 0):.3f}",
            "inline": True,
        })

    color = 0x27ae60 if not err_items else 0xe67e22  # green or orange

    embed = {
        "title": f"🌾 일별 파이프라인 완료 — {today}",
        "color": color,
        "fields": fields,
        "footer": {"text": f"성공 {len(ok_items)}개 / 실패 {len(err_items)}개"},
    }
    if err_items:
        embed["description"] = f"⚠️ 오류 품목: {', '.join(err_items)}"

    await send_discord(embeds=[embed])


async def notify_pipeline_error(error_msg: str, stage: str = "파이프라인"):
    """파이프라인 오류 알림"""
    embed = {
        "title": f"🚨 {stage} 오류 — {date.today()}",
        "description": f"```{error_msg[:1000]}```",
        "color": 0xe74c3c,  # red
        "footer": {"text": "즉시 확인 필요"},
    }
    await send_discord(embeds=[embed])


async def notify_sync_result(sync_result: dict):
    """데이터 동기화 결과 알림 (오류 있을 때만)"""
    errors = {k: v for k, v in sync_result.items() if isinstance(v, dict) and v.get("error")}
    skipped = {k: v for k, v in sync_result.items() if isinstance(v, dict) and v.get("skipped")}

    if not errors and not skipped:
        return  # 모두 정상이면 알림 없음

    lines = []
    for k, v in skipped.items():
        lines.append(f"⚪ {k}: API 키 없음 — 스킵")
    for k, v in errors.items():
        lines.append(f"🔴 {k}: {v.get('error', '알 수 없는 오류')}")

    embed = {
        "title": f"⚠️ 데이터 수집 경고 — {date.today()}",
        "description": "\n".join(lines),
        "color": 0xf4b942,  # gold
    }
    await send_discord(embeds=[embed])


async def notify_daily_report(report: dict):
    """일일 리포트 요약 알림"""
    today = report.get("report_date", str(date.today()))
    items = report.get("items", [])

    if not items:
        return

    # 위험도 top 2
    top2 = items[:2]
    fields = []
    for it in top2:
        rl = it.get("hotspot", {}).get("risk_level", "normal")
        re = RISK_EMOJI.get(rl, "⚪")
        fc = it.get("forecast", {})
        dir_e = DIR_EMOJI.get(fc.get("direction_14d", "neutral"), "➡️")
        fields.append({
            "name": f"{re} {it['item_name']} {dir_e}",
            "value": it.get("summary", "")[:80],
            "inline": False,
        })

    embed = {
        "title": f"📊 오늘의 농산물 위험 리포트 — {today}",
        "color": 0x3b9ae1,
        "fields": fields,
        "footer": {"text": "mk-map.com | AgriDigitalTwin"},
    }
    await send_discord(embeds=[embed])
