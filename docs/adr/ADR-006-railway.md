# ADR-006. 배포 — Railway (Dockerfile)

- Status: Accepted
- Date: 2026-07-04

## Context
소규모 팀이 인프라 관리 부담 없이 24/7 서버·스케줄러·DB를 운영해야 한다.

## Decision
Railway에 Dockerfile 빌드로 배포. healthcheck /health, 스케줄러(APScheduler)는 앱 프로세스 내 상주(Asia/Seoul). GitHub push → 자동 배포.

## Consequences
장점: 무중단 스케줄, 관리형 DB. 주의: 로컬 파일시스템 ephemeral(재배포 시 초기화) → 캐시/모델은 재생성 전제.
