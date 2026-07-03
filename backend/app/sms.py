"""SMS 발송 — 알리고(Aligo) 연동. 미설정 시 개발환경에서만 코드 노출.

운영에서 실제 문자를 보내려면 Railway 환경변수에 다음을 설정:
  SMS_PROVIDER=aligo
  ALIGO_API_KEY=...        (알리고 발급 API 키)
  ALIGO_USER_ID=...        (알리고 계정 ID)
  ALIGO_SENDER=01012345678 (사전 등록된 발신번호)
키 값 자체는 로그/커밋에 남기지 않는다.
"""
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

ALIGO_URL = "https://apis.aligo.in/send/"


def sms_configured() -> bool:
    s = get_settings()
    return bool(s.sms_provider == "aligo" and s.aligo_api_key and s.aligo_user_id and s.aligo_sender)


async def send_sms(phone: str, text: str) -> bool:
    """문자 발송. 성공 시 True. 미설정이면 False (호출부에서 개발 폴백 처리)."""
    s = get_settings()
    if not sms_configured():
        logger.warning("[sms] provider not configured; skipping real send")
        return False
    data = {
        "key": s.aligo_api_key,
        "user_id": s.aligo_user_id,
        "sender": s.aligo_sender,
        "receiver": phone,
        "msg": text,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(ALIGO_URL, data=data)
            j = r.json()
        # 알리고: result_code "1" 이면 성공
        ok = str(j.get("result_code")) == "1"
        if not ok:
            logger.error("[sms] aligo send failed: %s", j.get("message"))
        return ok
    except Exception as exc:
        logger.error("[sms] aligo request error: %s", exc)
        return False
