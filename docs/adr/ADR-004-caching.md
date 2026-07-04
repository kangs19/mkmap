# ADR-004. 캐시 — 현재 인메모리, Redis는 향후

- Status: Accepted
- Date: 2026-07-04

## Context
예측/신호 조회를 매 요청마다 DB에서 계산하면 낭비. PRD는 Redis를 지향하나 현재 단일 프로세스(Railway)라 인메모리로 충분.

## Decision
현재 app/cache.py 인메모리 TTL 캐시 사용(단일 프로세스). 수평 확장 시 Redis로 이관.

## Consequences
장점: 단순·무의존. 한계: 다중 인스턴스에서 캐시 불일치 → 확장 시 Redis 필요(향후 ADR 갱신).
