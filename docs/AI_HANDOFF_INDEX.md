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
- `https://mk-map.com` 기준 출시 체크는 12/12 통과했다.
- 운영 데이터는 2026-07-06 기준 signals, dashboard cards, item forecast API가 응답한다.
- 남은 공개 홍보 리스크는 `https://www.mk-map.com` 인증서/도메인 불일치다. 사용자가 `www`를 입력할 가능성이 있으면 Railway custom domain/DNS 또는 리다이렉트를 설정해야 한다.

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
- `docs/AI_SESSION_96_PRICE_LABEL_CONSISTENCY.md`
  - 2026-07-06 price label consistency.
  - Covers current-vs-forecast labeling across map pins, SVG path titles, and the right detail panel.
- `docs/AI_SESSION_97_MARKET_PANEL_CLEANUP.md`
  - 2026-07-06 cultivation and market panel cleanup.
  - Covers duplicate right-panel render cleanup, judgment-first market copy, validation, and follow-up QA.
- `docs/AI_SESSION_98_RISK_JUDGMENT_COPY.md`
  - 2026-07-06 risk judgment copy cleanup.
  - Covers readable risk text, duplicate risk function cleanup, current-state judgment wording, and validation.
- `docs/AI_SESSION_99_TREND_SIGNAL_COMPACTION.md`
  - 2026-07-06 trend signal compaction.
  - Covers repeated trend reason merging, icon summaries, grouped pressure signals, and validation.
- `docs/AI_SESSION_100_DASHBOARD_STATS_PANEL.md`
  - 2026-07-06 dashboard statistics panel.
  - Covers the expanded top `통계` view, priority rankings, anomaly/concentration statistics, no-data handling, and validation.
- `docs/AI_SESSION_101_WEATHER_LAYER_VISIBILITY.md`
  - 2026-07-06 weather layer visibility.
  - Covers weather badge markers, weather state judgment, map legend summary, duplicate function cleanup, and validation.
- `docs/AI_SESSION_102_WEATHER_DETAIL_JUDGMENT.md`
  - 2026-07-06 weather detail judgment.
  - Covers selected-region weather judgment cards, shared weather cache, crop-aware weather interpretation, and validation.
- `docs/AI_SESSION_103_MAP_HOVER_TITLE_FALLBACK.md`
  - 2026-07-06 map hover title fallback.
  - Covers final title/data-tooltip based custom popup fallback for SVG map regions and markers.
- `docs/AI_SESSION_104_WEATHER_MARKET_TAB.md`
  - 2026-07-06 weather judgment in cultivation/market tab.
  - Covers the new selected-region cultivation/shipment weather card, shared weather fallback reuse, and validation.
- `docs/AI_SESSION_105_LEAFLET_HOVER_FALLBACK.md`
  - 2026-07-06 Leaflet hover tooltip fallback.
  - Covers province/city path and pin Leaflet-native tooltip binding for map hover reliability.
- `docs/AI_SESSION_106_DEFAULT_PANEL_READABILITY.md`
  - 2026-07-06 default panel readability.
  - Covers larger right-panel briefing cards and judgment-first copy before a region is selected.
- `docs/AI_SESSION_107_TREND_REASON_COMPACT_DETAILS.md`
  - 2026-07-06 trend reason compact details.
  - Covers compact trend group judgments and collapsible detailed reasons in the selected-region forecast tab.
- `docs/AI_SESSION_108_LEGAL_PAGES_AND_SIGNUP_CONSENT.md`
  - 2026-07-06 legal pages and signup consent.
  - Covers `/privacy`, `/terms`, sitemap links, frontend legal links, and signup consent validation.
- `docs/AI_SESSION_109_LAUNCH_READINESS_CHECKER.md`
  - 2026-07-06 launch readiness checker.
  - Covers public production checks for health, app shell, legal pages, auth gates, weather, signals, dashboard cards, and item forecast APIs.
- `docs/AI_SESSION_110_PROMOTION_READY_UI_AUDIT.md`
  - 2026-07-06 promotion-ready UI audit.
  - Covers local frontend vendor assets, disabled beta control removal, onclick/duplicate-id audit, and launch UI smoke coverage.
- `docs/AI_SESSION_111_PUBLIC_PROMOTION_QA_COPY.md`
  - 2026-07-06 public promotion QA copy.
  - Covers unknown item-code frontend guard, removal of sample/beta launch copy, legal terms polish, browser hover QA, and the remaining `www` domain risk.
- `docs/AI_SESSION_112_PRICE_MAP_FORECAST_VISIBILITY.md`
  - 2026-07-06 price map forecast visibility.
  - Covers regional price API Korean key repair, launch readiness regional-price check, safer price pin rendering, and clearer map price status copy.
- `docs/AI_SESSION_113_PRICE_LAYER_FARMMAP_PRIORITY.md`
  - 2026-07-06 price layer FarmMap priority.
  - Covers the map style priority fix so `가격 예측` crop regions remain visible when the FarmMap overlay is enabled.
- `docs/AI_SESSION_114_ROBUST_MAP_HOVER_POPUP.md`
  - 2026-07-06 robust map hover popup.
  - Covers delegated document-level hover fallback for Leaflet SVG regions and marker pins, plus launch-readiness coverage.
- `docs/AI_SESSION_117_CUSTOMS_TRADE_AUDIT.md`
  - 2026-07-07 customs import/export API audit.
  - Covers verified Korea Customs Service endpoints, HS-prefix crop candidates, and feature-readiness decisions.
- `docs/AI_SESSION_118_CUSTOMS_TRADE_MODEL_INTEGRATION.md`
  - 2026-07-07 customs import/export feature integration.
  - Covers the new customs collector, training-table feature wiring, model retraining, and the decision not to promote the candidate yet.
- `docs/AI_SESSION_119_CUSTOMS_TRADE_STABILITY.md`
  - 2026-07-07 customs import/export stability pass.
  - Covers item-gated customs features, stricter crop matching, latest-month fallback, and bounded customs prediction overlays.
