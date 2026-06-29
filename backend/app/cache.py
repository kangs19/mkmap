"""
인메모리 캐시 — TTL 기반 단순 캐시
Redis 없이 단일 프로세스 환경(Railway)에서 예측 결과 재사용
"""
import time
from typing import Any, Optional

_store: dict[str, tuple[float, Any]] = {}  # key → (expires_at, value)


def get(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        del _store[key]
        return None
    return value


def set(key: str, value: Any, ttl: int = 300):
    """ttl: 초 단위, 기본 5분"""
    _store[key] = (time.time() + ttl, value)


def delete(key: str):
    _store.pop(key, None)


def clear_prefix(prefix: str):
    """특정 접두어로 시작하는 모든 키 삭제 (파이프라인 완료 후 무효화)"""
    keys = [k for k in _store if k.startswith(prefix)]
    for k in keys:
        del _store[k]


def stats() -> dict:
    now = time.time()
    live = sum(1 for exp, _ in _store.values() if exp > now)
    return {"total_keys": len(_store), "live_keys": live}
