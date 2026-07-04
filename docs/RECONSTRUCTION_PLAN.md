# MK-MAP 체계적 재구성 계획 (PRD/Engineering Bible 정렬)

작성: 2026-07-04. 목적: 기획서(Master PRD 20장 + Engineering Bible 7권)의 목표 아키텍처에 맞춰
**기존 자산을 보존하며** 단계적으로 재구성한다. 개발 루프:
`Analyze → Read PRD/Bible → Plan → Implement → Test → Fix → Docs → Commit → Check → Repeat`.

## 0. 보존 자산 (버리지 않음)
- 운영 URL: **mk-map.com** (Railway), GitHub **kangs19/mkmap**, PostgreSQL(운영)
- 데이터 파이프라인: KAMIS·KMA·KOSIS·MAFRA(agromarket 경락/저수율/출하비중)
- 작동 중 기능: 지도, 지역×품목, AI 예측(Champion/Challenger), 커뮤니티, 회원(휴대폰인증)
- ML: mkmap_meta(Feature 파이프라인) + build/train/predict + 챔피언/챌린저

## 1. 현재 상태 (Analyze)
- **백엔드**: FastAPI, routers 8 / models 14 / collectors 9 / API 73개. 잘 구축됨.
- **프론트**: 단일 `index.html` 2,587줄 (모놀리식). PRD 목표는 Next.js 모노레포.
- **DB**: 테이블이 daily_prices/forecasts/region_signals/community_* 등 존재하나
  PRD의 계층 네이밍(master_/raw_/core_/feature_/prediction_/community_/user_/system_) 미적용.
- **API 응답**: 원시 JSON. PRD 표준 envelope `{success,data,meta,error}` 미적용.
- **모듈 경계**: maps.py에 가격·날씨·저수율·출하·choropleth 혼재.
- **RBAC**: admin key + user role 있으나 공식 Role×Permission 매트릭스 미정립.

## 2. 목표 대비 격차 (Gap)
| 영역 | PRD/Bible 목표 | 현재 | 격차 |
|------|---------------|------|------|
| Region×Item | 모든 데이터의 기본 키 | 대체로 준수 | 코드 표준화 여지 |
| Frontend | Next.js 모노레포, 컴포넌트/상태관리 | 단일 index.html | **큼** |
| DB 계층 | master/raw/core/feature/prediction/community/user/system | 평면적 | 중 |
| API envelope | {success,data,meta,error}, /api/v1, RBAC | 원시 JSON | 중 |
| Feature Store | 중앙 feature_daily 테이블 | CSV(파일) | 중 |
| Model Registry | 버전·메트릭 저장 | 파일+DB혼재 | 소 |
| XAI | SHAP·자연어 설명 | 요인설명 있음 | 소 |
| 데이터 소스 명확화 | 산지가/도매가 혼동 금지(Ch.6) | KAMIS vs 경락 혼용 | 중(진행) |

## 3. 재구성 원칙
1. **점진적·무중단**: 운영 사이트를 깨지 않고 스트랭글러 패턴으로 정렬.
2. **기존 우선 활용**: 재작성보다 재구성(reorganize). 검증된 코드/데이터 보존.
3. **각 반복은 독립 배포 가능**: 한 슬라이스 = Plan→Implement→Test→Commit.
4. **문서 동기화**: 모든 변경은 docs 갱신.

## 4. 단계별 로드맵 (각 단계 = 루프 1회 이상)

### Phase 0 — 기반 정리 (저위험, 즉시)
- [ ] 저장소 문서 구조 정렬: docs/{PRD, Engineering, ADR, Runbooks} 하위 정리
- [ ] ADR 기록 시작 (ADR-001 Region×Item, ADR-005 AI/Community 분리, ADR-008 XAI)
- [ ] 이 계획서를 기준 문서로 등록

### Phase 1 — 데이터/소스 일관성 (중요·진행중)
- [ ] 가격 소스 명확화: KAMIS(차트·예측·모델) vs agromarket 경락가(지역) 라벨·단위 통일 (Ch.6)
- [ ] 품목별 단위 검증(마늘 10/20kg 등), 단위 메타 중앙화
- [ ] Feature Store 테이블화(feature_daily) — CSV→DB 이관 검토

### Phase 2 — API 표준화 (중위험)
- [ ] 표준 응답 envelope 도입(신규 엔드포인트부터, 기존은 점진)
- [ ] 라우터 도메인 분리: prices/weather/market/prediction/region 모듈화
- [ ] RBAC 매트릭스 정립(Guest/User/Farmer/Trader/Admin)

### Phase 3 — DB 계층 정렬 (중위험)
- [ ] 신규 테이블은 계층 네이밍 적용, 기존은 뷰/에일리어스로 점진 매핑
- [ ] 예측 이력·시장 데이터 immutable 정책 명문화

### Phase 4 — 프론트 컴포넌트화 (대공사, 선택)
- [ ] index.html을 기능 모듈로 분해(지도/우측패널/커뮤니티/모달)
- [ ] 장기: Next.js 모노레포 이관 (apps/web) — 별도 결정 필요

### Phase 5 — 확장 준비 (장기)
- [ ] 축산/수산 공통 구조(Region×Item) 검증, Multi-tenant 설계

## 5. 이번 반복의 GOAL 후보
- A. Phase 1 가격 소스/단위 일관성 마무리 (사용자가 방금 지적한 부분)
- B. Phase 2 API envelope + 라우터 도메인 분리 시작
- C. Phase 0 문서/ADR 정리 + 이 로드맵 확정

## 6. Check (완료 판정)
각 Phase 완료 시: 운영 무중단 확인 + 관련 문서 갱신 + 스모크 테스트 통과.
