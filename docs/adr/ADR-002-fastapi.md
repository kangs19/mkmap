# ADR-002. 백엔드 프레임워크 FastAPI

- Status: Accepted
- Date: 2026-07-04

## Context
Python 기반 데이터/ML 파이프라인과 동일 언어로 API를 운영해 마찰을 줄여야 한다.

## Decision
FastAPI + Uvicorn을 백엔드 표준으로 채택. 라우터는 /api/v1 네임스페이스.

## Consequences
장점: async, 자동 OpenAPI, Python ML 통합. 현재 73개 엔드포인트 운영 중.
