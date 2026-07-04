# MK-MAP 문서 인덱스

PRD/Engineering Bible 정렬 재구성의 기준 문서 허브. 모든 개발은
`Analyze → Read PRD/Bible → Plan → Implement → Test → Fix → Docs → Commit → Check → Repeat` 루프를 따른다.

## 0. 기준선
- [RECONSTRUCTION_PLAN.md](RECONSTRUCTION_PLAN.md) — 재구성 로드맵 (Phase 0~5), 격차분석
- 기획 원본: Master PRD 20장 + Engineering Bible 7권 (사용자 보관 docx)

## 1. ADR (Architecture Decision Records)
결정과 근거의 단일 출처. 새 결정은 ADR로 추가한다.
- [ADR-001](adr/ADR-001-region-item.md) Region × Item 기본 키
- [ADR-002](adr/ADR-002-fastapi.md) FastAPI 백엔드
- [ADR-003](adr/ADR-003-postgresql.md) PostgreSQL (Railway)
- [ADR-004](adr/ADR-004-caching.md) 캐시 (인메모리→Redis)
- [ADR-005](adr/ADR-005-ai-community-separation.md) AI/커뮤니티 분리
- [ADR-006](adr/ADR-006-railway.md) Railway 배포
- [ADR-007](adr/ADR-007-feature-store.md) Feature Store
- [ADR-008](adr/ADR-008-explainable-ai.md) 설명가능 AI
- [ADR-009](adr/ADR-009-champion-challenger.md) 모델 Champion/Challenger
- [ADR-010](adr/ADR-010-price-source-separation.md) 가격 소스 분리(KAMIS vs 경락)

## 2. Runbooks (장애 대응)
- [public-api-failure](runbooks/public-api-failure.md) 외부 공공API 장애
- [scheduler-failure](runbooks/scheduler-failure.md) 스케줄러/파이프라인
- [prediction-failure](runbooks/prediction-failure.md) 예측 실패/이상값
- [data-anomaly](runbooks/data-anomaly.md) 데이터 이상치
- [rollback](runbooks/rollback.md) 롤백

## 3. 파이프라인·데이터 문서 (기존)
- [MAFRA_API_PLAN.md](MAFRA_API_PLAN.md) — 농림부 오픈API 8종 분석·활용
- [PRICE_MODEL_PIPELINE.md](PRICE_MODEL_PIPELINE.md) — 가격 예측 모델
- [KMA_CROP_WEATHER_PIPELINE.md](KMA_CROP_WEATHER_PIPELINE.md) — 기상
- [KOSIS_PRODUCTION_PIPELINE.md](KOSIS_PRODUCTION_PIPELINE.md) — 생산량
- [BACKEND_IMPORT_PIPELINE.md](BACKEND_IMPORT_PIPELINE.md) — 백엔드 반영
- [API_SOURCE_MAPPING.md](API_SOURCE_MAPPING.md) — API 소스 매핑
- [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md) — 배포
- [MKMAP_2.0_PLAN.md](MKMAP_2.0_PLAN.md) — 2.0 방향
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — 현황

## 4. 골든 룰 (Engineering Bible)
1. Region × Item 구조를 절대 깨지 않는다.
2. AI 예측과 사용자 제보를 섞지 않는다.
3. 예측·시장 이력은 보존한다(immutable).
4. 모든 기능은 테스트 가능해야 한다.
5. 모든 API는 문서화된다.
6. 모든 릴리스는 관측 가능해야 한다.

## 5. 다음 반복
RECONSTRUCTION_PLAN의 Phase 1(가격 소스·단위 일관성) 또는 Phase 2(API 표준화) 진행.
