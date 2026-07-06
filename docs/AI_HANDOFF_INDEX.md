# MK-MAP AI Handoff Index

이 폴더는 Codex와 Claude Code가 같은 프로젝트를 이어서 작업하기 위한 인수인계 문서 묶음이다.

## 먼저 읽을 파일

1. `docs/AI_PROJECT_HANDOFF.md`
   - 프로젝트 전체 목적, 현재 상태, 주요 완료 작업, 운영 이슈, 다음 우선순위를 한 번에 본다.

2. `docs/AI_WORKFLOW_AND_STORAGE.md`
   - 데이터 저장 방식, 산출물 경로, API 키/환경변수 관리 원칙, 파이프라인 실행 순서를 본다.

3. `docs/AI_NEXT_ROADMAP.md`
   - 앞으로 해야 할 작업을 우선순위별로 본다.

4. `docs/AI_AGENT_WORKSTYLE.md`
   - Codex가 어떤 방식으로 작업했고, Claude Code가 이어받을 때 지켜야 할 작업 원칙을 본다.

## 앞으로 작업 후 반드시 업데이트할 것

작업자가 Codex든 Claude Code든, 의미 있는 변경을 끝냈으면 아래 파일을 갱신한다.

- 진행상태가 바뀌면 `docs/AI_PROJECT_HANDOFF.md`
- 저장 구조, 실행 명령, 환경변수가 바뀌면 `docs/AI_WORKFLOW_AND_STORAGE.md`
- 다음 작업 목록이 바뀌면 `docs/AI_NEXT_ROADMAP.md`
- 작업 규칙이나 주의사항이 추가되면 `docs/AI_AGENT_WORKSTYLE.md`

## 현재 가장 중요한 미해결 상태

- 로컬 코드와 GitHub CI는 정상이다.
- Railway 공개 서버는 최신 코드가 반영되어 KST 날짜 기준으로 응답한다.
- 하지만 운영 DB에는 2026-07-01 예측/신호 데이터가 아직 들어가지 않아 공개 API의 예측 결과가 비어 있다.
- 원격 admin pipeline 실행에는 Railway `ADMIN_KEY`가 필요하다. 로컬 `.env`에는 현재 `ADMIN_KEY`가 없다.

## Latest Model/Data Session

- `docs/AI_SESSION_81_ALL_ITEM_MODEL_BACKTEST.md`
  - 2026-07-06 all currently mapped crops model/data refresh.
  - Covers data collection, feature coverage, crop-specific features, model training/backtest, promotion result, public horizon policy, production application notes, and next work.
- `docs/AI_SESSION_82_ITEM_EXPANSION_20.md`
  - 2026-07-06 candidate expansion from 5 to 20 metadata items.
  - Covers KAMIS candidate audit, generated draft metadata, 20-item KAMIS collection, 20-item model backtest, promotion failure reasons, and next data-enrichment work.
- `docs/AI_SESSION_83_AGROMARKET_20ITEMS.md`
  - 2026-07-06 Agromarket regional price collection for 20 crops.
  - Covers KAMIS audit alias handling, Agromarket regional data collection, 20-crop model rerun, promotion result, and why the candidate is still experimental.
- `docs/AI_SESSION_84_ITEM_READINESS_GATE.md`
  - 2026-07-06 item-level forecast readiness gate.
  - Covers the new readiness audit script, item/horizon scoring, 20-crop candidate results, and next integration work for public artifact filtering.
- `docs/AI_SESSION_85_READINESS_PREDICTION_FILTER.md`
  - 2026-07-06 readiness-based prediction filtering.
  - Covers wiring item/horizon readiness into prediction and explanation artifacts, daily promotion integration, and public filtering behavior.
- `docs/AI_SESSION_86_READINESS_UX_COPY.md`
  - 2026-07-06 readiness UX copy and API summary.
  - Covers public readiness messages, backend response summaries, frontend held-horizon copy, and browser verification.
- `docs/AI_SESSION_87_PERIOD_READINESS_BUTTONS.md`
  - 2026-07-06 period readiness controls.
  - Covers blocked period buttons, public readiness notices, held-horizon forecast cells, and validation.
- `docs/AI_SESSION_88_MAP_READINESS_SURFACES.md`
  - 2026-07-06 map readiness surfaces.
  - Covers map color fallback, pin/hover readiness short-circuiting, and validation.
- `docs/AI_SESSION_89_READINESS_COUNT_CONSISTENCY.md`
  - 2026-07-06 readiness count consistency.
  - Covers the shared frontend public-horizon predicate and top explanation/statistics count fixes.
- `docs/AI_SESSION_90_BETA_QA_REGION_ENCODING.md`
  - 2026-07-06 beta QA region encoding.
  - Covers live beta user-flow checks and public API region-name mojibake sanitization.
- `docs/AI_SESSION_91_MOBILE_BETA_QA.md`
  - 2026-07-06 mobile beta QA.
  - Covers responsive layout fixes, mobile browser checks, and small-screen launch-readiness notes.
- `docs/AI_SESSION_92_AUTH_BETA_QA.md`
  - 2026-07-06 auth beta QA.
  - Covers public Korean auth error messages, safe no-SMS validation checks, and next launch QA slices.
- `docs/AI_SESSION_93_AUTH_MOBILE_POLISH.md`
  - 2026-07-06 auth mobile polish.
  - Covers mobile auth touch target sizing, Korean browser title, and local mobile browser verification.
- `docs/AI_SESSION_94_MAP_HOVER_QA.md`
  - 2026-07-06 map hover QA.
  - Covers stale map DOM hover binding, tooltip rebind behavior, and production drilldown verification plan.
- `docs/AI_SESSION_95_MAP_TOOLTIP_FALLBACK.md`
  - 2026-07-06 map tooltip fallback.
  - Covers CSS-only pin hover tooltips and native SVG path titles for launch-safe hover information.
