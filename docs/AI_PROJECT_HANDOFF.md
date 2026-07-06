# MK-MAP Project Handoff

## Latest Update - 2026-07-06 Session 105

See `docs/AI_SESSION_105_LEAFLET_HOVER_FALLBACK.md`.

Latest result:

- Added a Leaflet-native tooltip fallback to province/city map paths and crop pins.
- This keeps the existing custom hover popup, but gives the map engine its own hover card when DOM/title fallback is not visible to the user.
- Local whitespace and smoke validation passed.

## Latest Update - 2026-07-06 Session 104

See `docs/AI_SESSION_104_WEATHER_MARKET_TAB.md`.

Latest result:

- Added a selected-region weather judgment card to the `재배·시장` tab.
- The price tab continues to judge price impact, while the new market tab card judges cultivation/shipment impact from the same weather data.
- The new judgment uses rain, heat, cold, harvest progress, and shipment-year-over-year context to produce a practical read.
- Local whitespace and smoke validation passed.

## Latest Update - 2026-07-06 Session 96

See `docs/AI_SESSION_96_PRICE_LABEL_CONSISTENCY.md`.

Latest result:

- Tightened price labels across map pins, SVG path titles, and the right detail panel.
- Forecast-adjusted pin values now say `예측 도매가` or `예측 소매가`.
- SVG path fallback titles now say `현재` or `현재 평균`.
- Right detail panel now labels the base line as `현재 도매가` or `현재 소매가`.
- Local smoke suite passed.

## Latest Update - 2026-07-06 Session 95

See `docs/AI_SESSION_95_MAP_TOOLTIP_FALLBACK.md`.

Latest result:

- Added a simpler fallback for map hover information.
- Region pins now have both browser-native `title` and CSS-only `data-tooltip` hover content.
- SVG map paths now receive `title`, `aria-label`, and an SVG `<title>` child when DOM hover handlers bind.
- Local browser QA confirmed SVG path fallback title exists and console errors were empty.
- Production follow-up should confirm visible pins carry `data-tooltip` after deploy.

## Latest Update - 2026-07-06 Session 94

See `docs/AI_SESSION_94_MAP_HOVER_QA.md`.

Latest result:

- Reproduced the map hover complaint in browser QA.
- Found stale DOM-bound map nodes could keep `data-fm-dom-bound="1"` without a usable tooltip handler, causing redraw/drilldown hover cards to stop appearing.
- Updated marker/path DOM binding to rebind stale nodes.
- Added a document capture-phase hover fallback so Leaflet/SVG event bubbling is not the only path to show hover cards.
- Local browser QA confirmed visible map-path hover now shows `#map-tooltip` without console errors.
- Production province/city drilldown hover still needs final confirmation after deploy.

## Latest Update - 2026-07-06 Session 93

See `docs/AI_SESSION_93_AUTH_MOBILE_POLISH.md`.

Latest result:

- Checked the auth modal on a 390 x 844 mobile viewport after the auth API QA.
- The modal fit without horizontal overflow, but mobile auth fields were slightly small for older users.
- Increased mobile auth inputs, selects, and buttons to 44 px minimum height.
- Enlarged mobile auth helper/error message text.
- Changed the browser tab title from English to `MK-MAP 농산물 가격 예측`.
- Local mobile browser QA confirmed no overflow and no console errors.

## Latest Update - 2026-07-06 Session 92

See `docs/AI_SESSION_92_AUTH_BETA_QA.md`.

Latest result:

- Continued beta launch QA with member/auth error flows.
- Production invalid login, invalid email, farmer-without-phone, and invalid phone cases were checked without triggering real SMS sending.
- Phone/SMS validation now returns Korean public messages instead of FastAPI/Pydantic English validation text.
- `/api/v1/auth/me` now includes a Korean `로그인이 필요합니다.` message for frontend display.
- Added backend regression coverage for public Korean auth messages.
- Local validation passed with the smoke suite and backend API tests.

## Latest Update - 2026-07-06 Session 91

See `docs/AI_SESSION_91_MOBILE_BETA_QA.md`.

Latest result:

- Added responsive CSS for mobile/tablet launch readiness.
- The app now stacks map, filters, and right detail panel vertically on small screens.
- Mobile touch targets for nav, period buttons, checkboxes, tabs, and auth buttons were enlarged.
- Auth modal now fits inside phone-width screens.
- Browser QA at 390 x 844 showed no horizontal overflow and no console errors.
- Local validation passed with whitespace check, smoke suite, and backend API/horizon tests.

## Latest Update - 2026-07-06 Session 90

See `docs/AI_SESSION_90_BETA_QA_REGION_ENCODING.md`.

Latest result:

- Ran a production beta QA pass as a user: top navigation, period button, map pin drilldown, and right detail panel worked without console errors.
- Found public API region-name mojibake in `hotspot_region` values.
- Added canonical public region-name mapping for `KR-*` region codes.
- Public signal/dashboard/alert/report APIs now prefer clean Korean names such as `전남`, `경북`, and `제주` when the region code is known.
- Added regression coverage for canonical region names in public API payloads.
- Local API tests, smoke suite, and whitespace checks passed.

## Latest Update - 2026-07-06 Session 89

See `docs/AI_SESSION_89_READINESS_COUNT_CONSISTENCY.md`.

Latest result:

- Added a shared frontend predicate for public forecast horizons.
- Top explanation panel, statistics panel, hidden horizon list, blocked period checks, and horizon percentage calculation now use the same public-readiness logic.
- Horizons with `held_out: true` no longer count as available in top-level forecast readiness counts.
- Local validation passed with whitespace check, smoke suite, and backend forecast/API tests.

## Latest Update - 2026-07-06 Session 88

See `docs/AI_SESSION_88_MAP_READINESS_SURFACES.md`.

Latest result:

- Map forecast colors now fall back to a neutral color when the selected item/period is not public-ready.
- Map pins now show `검증 대기` instead of creating a synthetic future price for blocked periods.
- Map hover cards now show the public readiness reason and current/base price only for blocked periods.
- The same readiness gate is now shared by period buttons, compact forecast cells, map pins, and map hover cards.
- Local validation passed with whitespace check, smoke suite, and backend forecast/API tests.

## Latest Update - 2026-07-06 Session 87

See `docs/AI_SESSION_87_PERIOD_READINESS_BUTTONS.md`.

Latest result:

- Forecast period buttons now check item/horizon readiness before changing the active period.
- Blocked periods are shown with a dashed warning style, an accessibility disabled state, and a readiness reason.
- Clicking a blocked period keeps the current public forecast view and shows the public judgment message instead of generating a number.
- The compact forecast row now shows `검증 대기` and `공개 제외` for held-out periods.
- Local validation passed with the smoke suite and backend forecast/API tests.

## Latest Update - 2026-07-06 Session 83

See `docs/AI_SESSION_83_AGROMARKET_20ITEMS.md`.

Latest result:

- Agromarket regional price data was collected successfully for all 20 metadata crops.
- `scripts/audit_kamis_candidate_items.py` now recognizes existing metadata KAMIS mappings when UI labels do not exactly match KAMIS official item names.
- A 20-crop Agromarket candidate model was trained/backtested for 1, 14, 30, 90, and 180 day horizons.
- The candidate was not promoted. All horizons kept the existing checked baseline because temporal backtest stability was weaker than the baseline.
- Public production should keep the current checked baseline active. The 20-crop candidate outputs are experimental until KOSIS, KMA, FarmMap, and per-item reliability coverage are verified.

## Latest Update - 2026-07-06 Session 84

See `docs/AI_SESSION_84_ITEM_READINESS_GATE.md`.

Latest result:

- Added `scripts/audit_item_forecast_readiness.py`.
- The script combines metadata flags, feature cache coverage, training target rows, and per-item horizon backtest metrics.
- On the 20-crop Agromarket candidate model, 5 items were marked `candidate`: `cabbage`, `garlic`, `green_onion`, `onion`, `radish`.
- The 15 newly added crops were marked `hold` because their KOSIS/KMA/FarmMap/context coverage is not verified enough for trusted public forecasts.
- The next production step is to use this readiness report to filter public forecast artifacts by item and horizon.

## Latest Update - 2026-07-06 Session 85

See `docs/AI_SESSION_85_READINESS_PREDICTION_FILTER.md`.

Latest result:

- `scripts/predict_price_horizons.py` now accepts item-level readiness reports.
- Prediction artifacts now carry `held_out`, `available`, `readiness_status`, `readiness_reasons`, and `readiness_gate` per item/horizon.
- `scripts/explain_price_horizon_predictions.py` preserves those readiness fields in explanation artifacts.
- `scripts/run_daily_model_promotion.py` now creates an item readiness report and passes it into warn/strict prediction generation.
- Against the 20-crop Agromarket candidate, public-available horizons are limited to the better-mapped original crops and specific passing horizons.

## Latest Update - 2026-07-06 Session 86

See `docs/AI_SESSION_86_READINESS_UX_COPY.md`.

Latest result:

- Backend forecast and explanation responses now include a compact public `readiness` summary.
- Hidden horizons now carry user-facing Korean messages instead of only technical hold reasons.
- Frontend stores `forecast.readiness` and uses it for prediction-publication copy.
- Held periods are shown as `검증 대기`, with judgment text explaining why they are not public forecasts.
- The prediction explanation panel was browser-checked through localhost and the bad particle `배추은` was fixed to `배추는`.

마지막 업데이트: 2026-07-02 KST (세션13)

## 프로젝트 목적

MK-MAP은 농산물 가격 예측과 주산지 위험 신호를 결합하는 서비스다.

초기 대상 품목은 다음 5개다.

- `cabbage`: 배추
- `radish`: 무
- `onion`: 양파
- `green_onion`: 대파
- `garlic`: 마늘

목표는 단순 가격 차트가 아니라, 다음 정보를 조합해 사용자가 볼 수 있는 예측과 설명을 만드는 것이다.

- KAMIS 가격
- AT 지역별 도소매 가격
- AT 공영도매시장 정산정보
- KOSIS 생산량/재배면적
- KMA 작물별 농업주산지 상세날씨
- RDA 농업기상 관측자료
- 기상특보, 태풍, 영향예보, 중기예보
- 위성영상, 일기도 같은 forecast context

최종 사용자 관점의 산출물은 다음이다.

- 품목별 14일 가격 방향 예측
- 상승 확률, 급등 확률, 바닥 확률
- 주산지별 위험 점수
- 어떤 요인이 예측에 영향을 줬는지 설명
- 지도/대시보드/위젯/API에서 쓸 수 있는 정리된 JSON

## 현재 저장소와 운영 정보

- GitHub: `https://github.com/kangs19/mkmap`
- 공개 백엔드: `https://mk-map.com`
- API 문서: `https://mk-map.com/docs`
- 배포 대상: Railway
- Railway 설정 파일: `railway.toml`
- Docker 진입: `Dockerfile`, `start.sh`

비밀값은 문서와 Git에 넣지 않는다.

## 현재 완료된 큰 작업

### 1. GitHub/CI 안정화

여러 차례 CI 실패 메일이 왔고, 원인은 로컬 코드와 CI 환경 차이, API 진단 스크립트 실패 처리 부족, 일부 스크립트 컴파일 누락 등이었다.

현재는 다음 커밋들 이후 GitHub Actions CI가 연속 성공 상태다.

- `40c3830 Add RDA agri weather live diagnostic`
- `ffb56f6 Add KMA forecast context diagnostics`
- `fc3eee3 Harden cached event collection`
- `effeb7a Collect cached AT price sources`
- `e1866d0 Add bounded weather collection for daily pipeline`
- `2ffdc79 Use bounded weather pipeline in backend runners`
- `31978cc Use KST dates for backend public data`
- `307b59b Add AI handoff documentation`

### 2. API 서비스 카탈로그 정리

`config/api_services.json` 기준 현재 12개 서비스가 관리된다.

- KAMIS 가격
- KOSIS 생산 통계
- AT 지역별 품목별 도소매 가격
- AT 전국 공영도매시장 정산정보
- RDA 농업기상 상세 관측데이터
- KMA 작물별 농업주산지 상세날씨
- KMA 기상특보
- KMA 영향예보
- KMA 태풍정보
- KMA 중기예보
- KMA 위성영상
- KMA 일기도

`python scripts/smoke_api_services.py` 실행 시 12개 서비스가 모두 configured로 잡히도록 정리했다.

### 3. 라이브 API 진단 확장

중앙 진단 스크립트:

```powershell
python scripts\run_live_api_diagnostics.py --date 2026-07-01 --item cabbage --max-rows 2 --no-write
```

현재 진단은 다음을 구분한다.

- `ok`: 데이터 수집 성공
- `no_data`: 제공자는 응답했지만 해당 날짜/조건 데이터 없음
- `api_error`: 제공자 API 오류
- `http_error`: HTTP 오류
- `timeout`
- `missing_env`
- `mapping_required`
- `failed`

2026-07-01 기준 진단에서 코드 실패는 없고, 제공자 상태로 남은 것은 주로 다음이다.

- KMA 기상특보: `DB_ERROR`
- KMA 위성영상: `HTTP_403`
- 일부 서비스: 날짜 조건상 `NO_DATA`

### 4. 가격 수집 다중 소스화

이전에는 가격 캐시가 사실상 KAMIS 중심이었다.

현재 `scripts/collect_live_price_features.py`는 기본적으로 다음 세 소스를 모두 수집한다.

- `kamis_price`
- `at_regional_price`
- `at_market_settlement`

기본 수집 기간은 90일이다.

```powershell
python scripts\collect_live_price_features.py --date 2026-07-01
```

주의:

- AT 정산가격은 정확한 품목 코드 매핑이 있는 품목만 활성화한다.
- 배추/무는 잘못된 광범위 검색 결과가 섞일 수 있어 정산 매핑을 일부러 활성화하지 않았다.
- 양파, 대파, 마늘은 일부 정산 매핑이 있어 수집된다.

### 5. 날씨 수집 안정화

KMA 작물별 농업주산지 상세날씨는 품목/지역/작형 조합이 많고, 제공자 응답 지연이 자주 있다.

그래서 다음 옵션을 추가했다.

```powershell
python scripts\collect_live_weather_features.py `
  --date 2026-07-01 `
  --lookback-days 3 `
  --max-requests-per-item 16 `
  --request-timeout-seconds 8
```

요청 상한이 있을 때 한 날짜에만 몰아서 쓰지 않고, lookback 날짜별로 샘플 요청을 분산한다.

### 6. 엔드투엔드 로컬 파이프라인 검증

운영 DB import 없이 로컬에서 다음이 성공했다.

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --skip-collect --skip-backend-import
```

2026-07-01 로컬 산출 결과:

- 위험신호: 85행
- 가격 학습 테이블: 150행
- 예측: 5개
- 모델 학습: 성공
- 위험도 보정 예측: 성공

### 7. KST 날짜 버그 수정

Railway 서버는 UTC 기준으로 동작할 수 있어서, 한국 시간 2026-07-01 새벽에도 `date.today()`가 2026-06-30으로 나오는 문제가 있었다.

수정:

- `backend/app/timezone.py` 추가
- `kst_today()`, `kst_now()` 도입
- public API, scheduler, admin pipeline 기본 날짜를 KST 기준으로 변경

확인 결과:

- `https://mk-map.com/api/v1/signals/today`가 이제 `base_date: 2026-07-01`로 응답한다.

## 현재 운영 서버 상태

2026-07-01 KST 기준 공개 서버 확인:

- `/health`: 정상
- `/api/v1/signals/today`: `base_date`는 2026-07-01로 정상이나 `items`는 빈 배열
- `/api/v1/dashboard/cards`: 품목 카드 5개는 나오지만 예측/위험/가격 값은 null
- `/api/v1/items/cabbage/forecast`: 404
- 로컬 `.env`에는 API 키와 `ADMIN_KEY`를 채웠다. 실제 값은 Git/문서에 기록하지 않는다.
- 로컬 `.env`의 기본 endpoint/operation 설정도 채웠다. `KAMIS_CERT_ID`는 코드 fallback과 같은 `mkmap`으로 명시했다.
- `KOSIS_PRODUCTION_TBL_ID`는 의도적으로 비워둔다. 품목별 KOSIS 통계표가 달라서 `metadata/items/*.json`의 `external_mappings.kosis_production.tbl_id`를 사용한다.
- `/api/v1/admin/status`: 로컬 `ADMIN_KEY`로 호출 시 503. 운영 Railway에 `ADMIN_KEY`가 없거나 로컬 값과 다를 가능성이 높다.

해석:

- 최신 코드 배포는 반영됐다.
- 날짜 기준 버그는 해결됐다.
- 하지만 운영 DB에는 아직 2026-07-01 `region_signals`와 `forecasts`가 들어가지 않았다.
- 공개 API 산출물 상태는 `scripts/verify_public_api_outputs.py`로 자동 검증할 수 있다.

확인된 원인과 수정 내역 (세션2):

1. **Dockerfile COPY 누락** (커밋 83c1b3b): `/app/scripts/`, `/app/mkmap_meta/`, `/app/config/`가 컨테이너에 없어서 pipeline subprocess 자체가 실패했다. 수정 완료.
2. **collect_live_price_features.py 전체 실패** (커밋 007c306): `DATA_GO_KR_API_KEY` 미설정 시 AT, KAMIS 모두 block. 서비스별 개별 체크로 변경해 KAMIS는 독립 실행 가능하게 수정. 수정 완료.
3. **Railway `ADMIN_KEY` 미설정**: admin endpoint 503 원인. 사용자가 직접 Railway Variables에 추가 필요.

현재 상태 (세션3 업데이트):

**로컬 파이프라인 전체 성공 확인 (2026-07-01)**
- Codex 경로: `C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git`
- `.env` 파일 위치: 위 Codex 경로. GitHub에 없음. 실제 API 키 포함.
- 실행 결과: signals 85행, forecasts 5개, 모델 학습 성공 (MAE 0.013)
- 로컬 SQLite DB에 import 완료

**추가 수정 커밋 (ecd6994)**
- collect_live_weather_features: TimeoutError 처리 추가
- run_meta_pipeline: 날씨 수집 soft_fail 처리
- build_price_training_table: min_required_history 28→14, ma_28 안전 슬라이싱

**Railway 운영 DB 미반영 원인**:
- Railway Variables에 API 키가 없음 (로컬 .env에만 있음)
- Railway에서 pipeline이 실행되면 자체 Variables를 읽음
- 해결 방법 2가지:
  1. Railway Variables에 API 키 추가 → auto-recover가 자동 실행
  2. 또는: 로컬에서 생성된 data/ 파일을 Railway admin API로 import

**세션4 추가 완료:**
- `scripts/push_outputs_to_server.py` (커밋 3d88171): 로컬 파이프라인 출력을 Railway DB에 HTTP POST로 import하는 스크립트 추가
- `backend/app/routers/admin.py` (커밋 3d88171): `POST /api/v1/admin/import-outputs` 엔드포인트 추가 — 로컬 JSON을 바로 DB에 삽입 가능
- `backend/app/routers/admin.py` (커밋 41b20c6): pipeline status 개선 — step별 summary, duration, last_step_completed/failed 저장
- `start.sh` (커밋 85049a6): `export APP_ENV="${APP_ENV:-production}"` 추가 — Railway에서 APP_ENV 미설정 시 development 모드로 뜨는 버그 수정
- **RDA 농업기상 완전 수정** (커밋 0c1efe9):
  - `weather.py` `_xml_to_payload` 루트 태그 wrapping 수정 → `extract_rows`가 RDA XML 파싱 가능
  - `normalizers.py` `public_api_error` RDA 성공코드 `"200"` 처리 추가
  - `weather.py` `RdaAgriWeatherConnector.fetch_weather` 품목별 관측소 쿼리 + 전월 폴백
  - `weather.py` `obsr_Spot_Cd/Nm` 필드 → region_code/name 추출에 추가
  - 전체 5개 품목 메타데이터에 `rda_weather.obsr_spot_codes` 추가 (219개 관측소에서 주산지 기반 선정)
  - 실측: 배추 540개, 마늘 210개, 양파 210개, 대파 180개, 무 330개 feature 수집 성공
- **verify 엔드포인트** (커밋 19fa179): `POST /api/v1/admin/meta-pipeline/verify` — DB에서 오늘 날짜 signals/forecasts 존재 여부 품목별 체크
- verify_public_api_outputs 재확인: 서버 alive, 날짜 정확, 7/8 체크 missing_data (Railway DB 미반영 확인됨)

로컬 `.env` 보정 후 라이브 진단:

- `missing_env`: 0
- KAMIS 가격: ok
- AT 지역별 가격: ok
- AT 정산정보: ok
- KOSIS 생산통계: ok
- KMA 중기예보: ok
- KMA 작물별 농업주산지 상세날씨: 일부 ok, 일부 `NO_DATA`
- RDA 농업기상: `NO_DATA`
- KMA 기상특보: provider `DB_ERROR`
- KMA 위성영상: provider/auth `HTTP_403`
- KMA 일기도: provider `NO_DATA`

**세션6(2) 추가 완료 (2026-07-01):**
- **index.html nav 링크** (커밋 bff0c80): "가격 예측" 버튼 → `<a href="/forecast-explanation">` 링크로 변경
- `map_viewer/templates/forecast_explanation.html` 및 `admin.html` 존재 확인 (route와 파일 매핑 정상)
- **import 검증 강화** (커밋 506bdd9): forecasts<5 실패 처리, signals<50 경고 추가
- **Codex 클론 sync** (b6dbe68까지 fast-forward)
- **로컬 파이프라인 실행 완료** (2026-07-01, --skip-collect):
  - 훈련 행: **1123개**, direction_accuracy: **78.2%** (test), 백테스트 **87.5%**
  - 예측 5개 품목 생성 (base_date 2026-06-30)
  - 로컬 DB import: signals 85행, forecasts 5개 완료 (ok: true)

**세션6 추가 완료 (2026-07-01):**
- **FastAPI 라우트 추가** (커밋 877b9e5):
  - `/admin-panel`, `/admin-panel.html` → `map_viewer/templates/admin.html` 서빙
  - `/forecast-explanation`, `/forecast-explanation.html` → `map_viewer/templates/forecast_explanation.html` 서빙
- **운영 서버 상태 재확인** (2026-07-01):
  - `/health`: `{"env":"development"}` — Railway에 `APP_ENV=development` 명시 설정 또는 미설정으로 config.py 기본값(`development`)이 사용 중
  - `/api/v1/admin/status`: `503 ADMIN_KEY is not configured` — Railway에 ADMIN_KEY 없음 확인
- **365일 가격 수집 완료**:
  - KAMIS: 배추 3572건, 마늘 4698건, 대파 3402건, 양파 3382건, 무 3712건 (vs 30일 기준 280건)
  - AT regional price: 100~358건/품목
  - AT market settlement: 양파 245건, 나머지 0건 또는 HTTP_502
- **파이프라인 재실행 완료 (세션6)**:
  - 훈련 행: **1118행** (vs 25행 — 45배 개선)
  - 모델 MAE: 0.024, sign_accuracy: 57.1%, direction_accuracy: **81.7%**
  - 백테스트 direction_accuracy: **87.5%**, confidence: **"high"**
  - 품목별 모델: garlic (MAE ratio 0.42, 채택), green_onion (direction +8.7%p 개선, 채택)
  - 예측 5개 품목 모두 생성 완료 (base_date 2026-06-29)

**세션5 추가 완료:**
- **P2 모델 품질 개선** (커밋 59c53e8):
  - 훈련 데이터 현황 파악: KAMIS 캐시 20날짜, 실제 훈련 행 25개 (5 품목 × 5행)
  - `build_price_training_table.py`: AT 도매가 별도 추출, price_pct_of_hist_mean/at_wholesale_norm 피처 추가
  - `train_price_baseline_model.py`: 절대가격 피처(avg_price, lag_*_price 등) 모델에서 제외 → 품목 간 스케일 혼동 방지
  - 365일 데이터 수집 중 (`collect_live_price_features.py --days-back 365`)
- **P3 Discord 알림 강화** (커밋 b35ed7d):
  - `scheduler.py`: pipeline 성공 후 DB에서 `signal_count`, `forecast_count` 쿼리 후 Discord 전송
  - `notify.py`: `notify_pipeline_success` 개선 — signal/forecast 수 + 로그 3줄 code block embed
- **P2 프론트 UI 개선** (커밋 b0ef561):
  - `#data-status-pill` 헤더 추가 — live(초록)/nodata(주황)/loading(회색) 상태 + 애니메이션 dot
  - `fetchLiveData()` 개선: `LIVE_BASE_DATE`, `LIVE_ITEM_COUNT` 저장; items=[] 시 "예측 데이터 준비 중" 표시
  - `renderMiniCards()` 개선: live 데이터 없는 품목은 위험도 "—" 표시; 전체 no-data 시 안내 배너
  - `showRegionDetail()` 개선: `rp-update-lbl`에 `LIVE_BASE_DATE` KST 기준 표시
  - null-safe 가격 표시: `pv=0` → `"—"` (기존 `"0원"` 레이아웃 깨짐 수정)
  - null-safe 예측셀(7/30/90일), yoy, chgPct 전부 `"—"` 처리

## 현재 운영 서버 상태 (2026-07-01 세션11 업데이트)

**완료됨:**
- Railway Variables 설정 완료: ADMIN_KEY(rotated), KAMIS_API_KEY, DATA_GO_KR_API_KEY, KOSIS_API_KEY, KMA_API_KEY, APP_ENV=production
- `/health` → `{"env":"production", "scheduler":true, "version":"0.3.0"}` 정상
- **공개 API 8/8 전부 통과** ✓
- **PostgreSQL 영구 저장** (커밋 a1b5465): 재배포해도 DB 유지됨
- **KAMIS periodProductList + httpx** (커밋 4753a3d + ebbc50d): change_30d_pct 실값 정상화
- **현재 DB 상태 (PostgreSQL, 세션11)**:
  - `daily_prices`: ~4,000건 (2024-07-01~2026-07-01, 2년치)
  - `daily_weather`: ~4,400건
  - `region_signals`: 85건 (2026-07-01)
  - `forecasts`: 5건 (이전 로컬 push값 유지)
- **change_30d_pct 실값**: cabbage+2.4%, radish+5.9%, onion+15.7%, green_onion-7.0%, garlic 수정 중

**세션11 핵심 수정 (커밋 341b8f9~d0c4b8e):**
- **Railway 모델 훈련 자동화** (커밋 341b8f9):
  - `scripts/export_db_prices_to_cache.py` — PostgreSQL `daily_prices` → kamis_price JSON 캐시 파일 생성
  - `run_meta_pipeline.py`에 "Export DB prices to cache" step 추가 (soft_fail=True)
  - Railway에서 90일치 DB 데이터로 모델 훈련 가능 → forecasts 자동 생성 기대
- **pipeline exit code fix** (커밋 a24e251): signals_ok이면 exit 0 (forecasts 없어도 계속)
- **scheduler KAMIS/KMA sync** (커밋 a24e251): 매일 06:00 KST 자동 sync 추가
- **garlic 단위 버그** (커밋 a7bdd23):
  - periodProductList kindcode=03(깐마늘) → 1kg 기준, 기존 DB 데이터는 10kg 기준
  - `_PERIOD_UNIT_MULTIPLIER["garlic"] = 10.0` 추가 → 단위 정합
  - `POST /admin/debug/fix-garlic-prices` 엔드포인트 추가 (잘못된 행 삭제 + 재sync)
- **garlic 진단** (커밋 d0c4b8e): `GET /admin/debug/garlic-prices` 추가

**남은 문제:**
- garlic DB 데이터 단위 정합 확인 및 재sync 필요
- AT settlement 429 — 매일 쿼터 소진, 자정(KST) 리셋 후 재시도
- Railway forecasts 자동화 검증: 다음 06:00 KST 스케줄러 실행 후 forecasts 생성 여부 확인

## 재배포 후 절차 (PostgreSQL 전환 후)

PostgreSQL은 영구 저장소이므로 재배포 후 DB 초기화 없음.
단, signals/forecasts는 로컬 파이프라인 실행 후 push 필요:

```powershell
# 1. 로컬 파이프라인 실행 (날씨 제외, 빠른 버전)
cd "C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git"
python scripts\run_meta_pipeline.py --date YYYY-MM-DD --skip-weather

# 2. 예측/신호 재주입
python scripts\push_outputs_to_server.py --date YYYY-MM-DD --server https://mk-map.com

# 3. KAMIS sync (새 날짜 가격 채우기)
# POST https://mk-map.com/api/v1/admin/sync/run?source=kamis&days_back=7&background=false

# 4. KMA weather sync (source=kma, weather 아님!)
# POST https://mk-map.com/api/v1/admin/sync/run?source=kma&days_back=3&background=false
```

## 세션12 완료 항목 (2026-07-01)

최신 커밋: dea8732

**코드 감사 수정 (20개 이슈):**
- CRITICAL: signals.py 날짜 중복 제거, UniqueConstraint+UPSERT, 마늘 연도 경계, database.py 이중변환, training table 최소행 계산
- WARNING: sync.py failed_items 반환, admin.py COUNT before DELETE, scheduler 개별 로깅
- INFO: import_meta_outputs ok/forecasts_ok 분리, training 0행 exit 1, predict FileNotFoundError soft-fail

**추가 버그 수정:**
- `start.sh`: PostgreSQL 환경에서 mock data seed 완전 방지 (매 배포마다 mock 재생성 버그)
- `database.py`: init_db() 시 UniqueConstraint 마이그레이션 (CREATE UNIQUE INDEX IF NOT EXISTS)
- `run_meta_pipeline.py`: build_price_training_table soft_fail=True (0행 exit 1 후 파이프라인 블로킹 방지)

## 다음 우선순위

1. AT settlement 90일 재수집 (자정 KST 리셋 후) → 로컬 파이프라인 재실행 + push
2. Railway 다음 06:00 KST 스케줄러 실행 후 forecasts 자동 생성 확인
3. (완료됨) garlic DB 단위 정합 — fix-garlic-prices + mock cleanup 이미 실행됨

```powershell
# garlic 진단 (Railway 배포 후)
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/debug/garlic-prices?days=35" -Headers @{"X-Admin-Key"=$admin_key}

# AT settlement 재수집 (자정 이후)
cd "C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git"
python scripts\run_meta_pipeline.py --date 2026-07-02 --price-days-back 90 --skip-weather
python scripts\push_outputs_to_server.py --date 2026-07-02 --server https://mk-map.com
```

**세션8 추가 완료 (2026-07-01):**
- **AT settlement 코드 발견 및 추가** (커밋 cbc696a):
  - AT settlement API lclsf 코드 전수 탐색 결과:
    - lclsf=10 → 엽경채류 (배추 포함)
    - lclsf=11 → 근채류 (무 포함)
    - lclsf=12 → 조미채소류 (대파, 마늘 등)
  - `metadata/items/cabbage.json`: `at_settlement` 추가 — lclsf=10, mclsf=01(배추)
  - `metadata/items/radish.json`: `at_settlement` 추가 — lclsf=11, mclsf=01(무)
  - 배추/무 AT settlement 수집 테스트 성공 (배추 11건/14일, 무 확인 완료)
- **at_wholesale_norm 분석**: 기존 fill rate 문제 원인 파악
  - green_onion: 코드 올바름(lclsf=12, mclsf=02), AT API 502 에러가 주원인 (API provider 측 불안정)
  - cabbage/radish: AT settlement 매핑 자체가 없어서 0건이었음 → 이번 세션에서 해결
- **Railway 영구 스토리지 없음 확인**: 매 배포마다 data/ 초기화, --days-back 365 유지 필요
- **원격 파이프라인 진행 중**: KAMIS SSL fix(6a247c4) 적용, 365일 수집 중

**남은 문제:**
- `dashboard_cards` price_non_null=0 — 운영 DB `daily_prices` 미채움 (원격 파이프라인 성공 후 채워짐)
- 원격 파이프라인 아직 KAMIS 수집 중 (365일 × 5품목 = ~27분)
- 다음 파이프라인 실행 시 배추/무 AT settlement 데이터가 처음으로 수집됨
- at_wholesale_norm 개선 확인: 다음 pipeline 실행 후 training table에서 cabbage/radish fill rate 확인 필요

## 세션13 완료 항목 (2026-07-02)

최신 커밋: c93e0b0

**PostgreSQL UPSERT 안정화:**
- `sync.py`: `on_conflict_do_update(constraint=...)` → `index_elements=[...]` 방식으로 변경 — named constraint 없이도 작동
- `database.py`: init_db() startup migration에서 duplicate rows 제거 후 `CREATE UNIQUE INDEX IF NOT EXISTS` 실행 (이전에는 중복 때문에 index 생성 실패 → UPSERT 전체 fail → saved=0)
- `models/market.py`: `DailyMarket`에 `UniqueConstraint("item_code", "date", "source", ...)` 추가
- `sync.py` `sync_market_volume()`: PostgreSQL UPSERT 방식으로 업그레이드 (SQLite fallback 유지)
- `database.py`: daily_market도 dedup + unique index migration 추가

**오늘(2026-07-02) 파이프라인 완료 및 Railway push:**
- 로컬 파이프라인 실행: 신호 85건, 예측 5개 생성
- Railway push 완료: `signals_imported=85`, `forecasts_imported=5`
- verify endpoint 12/12 체크 전부 통과 (`ok=true`)

**Railway 상태:**
- 최신 배포 코드: c93e0b0 (2026-07-02)
- 다음 Railway 재배포 시 init_db()에서 duplicate 제거 + unique index 생성 자동 실행
- 이후 KAMIS sync가 UPSERT로 정상 작동 예상

## 현재 완성도

코드와 로컬 파이프라인 기준:

- 약 85%

운영 서비스까지 포함:

- 약 78%

UPSERT 안정화로 Railway DB sync가 이제 올바르게 작동해야 한다. 다음 06:00 KST 스케줄러가 실행되면 Railway에서 자동으로 pipeline + sync가 진행된다.
## Session 32 - Main UI/UX renewal and horizon forecast deploy prep (2026-07-05)

Completed:

- Renewed `index.html` into an operational price-forecast dashboard.
- The first screen now focuses on item selection, multi-horizon forecast cards, forecast reasons, risk map, item comparison, high-risk alerts, and data-source status.
- Added `backend/app/services/horizon_forecasts.py`.
- Updated `backend/app/routers/forecasts.py` so forecast/explanation APIs first try active horizon prediction artifacts and fall back to DB forecasts if artifacts are absent.
- Added active horizon config:
  - `ACTIVE_PRICE_MODEL_PREFIX`
  - `ACTIVE_PRICE_PREDICTIONS_PATH`
  - `ACTIVE_PRICE_EXPLANATIONS_PATH`

Deployment note:

- Remote `origin/main` had newer operational commits, so this work was rebased on top of `origin/main`.
- Rebase policy:
  - keep remote fixes for collectors, DB, scheduler, and pipeline
  - keep the renewed `index.html`
  - reapply minimal horizon forecast API wiring
- Generated `data/` artifacts were intentionally not committed.

Important caveat:

- The renewed UI deploys immediately with the code.
- File-based horizon forecasts require strict prediction/explanation artifacts under `data/model` or explicit `ACTIVE_PRICE_*_PATH` variables.
- If artifacts are absent on Railway, the forecast endpoint falls back to DB-backed forecasts.
# Session 39 - Align hover, pin, and right-panel map prices (2026-07-05 KST)

- User feedback: the mouse-hover popup price and the right detail-panel price did not match for the same map selection.
- Root causes fixed:
  - Province/city paths could pass either `KR-42`-style codes or short Korean names such as `강원`, so regional price lookup could fall back differently by surface.
  - Hover-card fallback prediction used raw local deviation while the right detail panel used period-aware `periodForecastPct(...)`.
  - Some city price pins did not pass an explicit province code, making regional price enrichment less consistent.
- Added `normalizeSidoCode(...)` and `getRegionPriceContext(...)` so map pins, hover cards, and right detail panels share one regional price context.
- Hover-card fallback predicted price now uses the same selected-horizon calculation as the right detail panel.
- Hover-card current-average unit now uses the item unit such as `10kg` instead of hardcoded `/kg`.
- Local verification:
  - Smoke suite passed.
  - Browser check loaded the map with 4 province pins and no runtime errors.
  - Province hover for 강원 showed `5,342원/10kg`, matching the province pin.
  - City-level 평창군 pin showed `5,137원/10kg`, and the right panel showed predicted price `5,137원` with current price `5,763원 / 10kg`.

# Session 40 - Move trend analysis into forecast tab and repair drilled-map hover (2026-07-05 KST)

- User feedback: `기간별 가격 동향 분석` belongs inside the price-forecast experience, and hover popups did not appear after drilling into the middle/city map level.
- Moved the `기간별 가격 동향 분석` section from the `재배·시장` tab into the `가격 예측` tab, directly below the multi-horizon forecast cells.
- Fixed map pin hit areas:
  - `.region-pin` now accepts pointer events and uses a pointer cursor.
  - Province and city Leaflet price pins now use real icon sizes instead of `iconSize:[0,0]`.
  - Added `bindMarkerDomEvents(...)` to bind `mouseenter/mouseover/pointerover`, move, leave, and click directly to marker DOM elements. This makes hover cards work even when Leaflet marker events are unreliable after drill-down.
- Local verification:
  - Smoke suite passed.
  - Browser inspection confirmed `rp-trend-reasons` now lives under `rp-pane-forecast`.
  - Province markers render with 110x58 hit areas; city markers render with 116x64 hit areas and direct DOM event binding.

# Session 41 - Data trust labels, working top tabs, and clearer dashboard (2026-07-05 KST)

- User feedback: 재배·시장 탭의 정보가 검증된 값인지 임의값인지 확인 필요. Top `가격 예측 설명` tab did not feel functional, and dashboard was hard to read.
- Audit result:
  - Verified/live-style values: regional/national prices from map price APIs, regional price data, shipment-share API where available.
  - Model/derived values: annual production/shipment, production share fallback, risk breakdown when no direct signal exists, daily quantity converted from annual amount.
  - Removed/blocked unverified values: import volume is now shown as `미연동` instead of a made-up percentage/tonnage.
- Removed random UI data:
  - `renderPriceChart(...)` no longer generates random fallback price history. If no price history API rows are available, the chart area states that history data is not available.
  - Right-panel risk breakdown no longer uses `Math.random()`. Scores are deterministic and labelled as live/model.
- Added source badges:
  - `실데이터`: API/cache source.
  - `모델`/`추정`: derived from available data.
  - `미연동`: do not display fabricated numbers.
- Changed top nav `가격 예측 설명` and `대시보드` from external links to working in-page panels.
- Dashboard panel now summarizes prediction count, price collection count, warning/high count, upward-bias count, and prioritized item cards.
- Local verification:
  - Smoke suite passed.
  - Browser check confirmed top explanation panel opens, dashboard panel opens, and map returns correctly.
  - Detail stats tab shows labels such as `대표 도매가 실데이터`, `일평균 환산량 추정`, and `수입/대체 공급 미연동`.

# Session 38 - Hover-only map cards and clearer market/share context (2026-07-05 KST)

- User feedback: click drill-down must not leave a fixed popup on the map; hover cards should appear only while hovering. Also requested clearer wholesale/retail market influence, better card sizing, and no blank national-share fields.
- Removed all `openRegionPopup(...)` click behavior. Map clicks now only update the right detail panel and/or drill into a region. The map information card is hover-only again.
- Increased hover card width to reduce awkward wrapping and shortened long city lists to the first four names plus `외 N곳`.
- Added `influenceMarketFor(...)` to show the representative affected wholesale market/market zone in the hover card. This is displayed as an influence/reference market, not as a claim that every regional price comes from one exact market.
- Added production/share fallback helpers so `전국 비중` can use shipment/production ton share when official production share is absent.

# Session 37 - UI audit hardening after map-region correction (2026-07-05 KST)

- Follow-up after user correctly challenged insufficient verification.
- Added a browser runtime error capture hook (`globalThis.__codexErrors`) so future UI audits can distinguish "no visible issue" from actual runtime errors.
- Fixed a race condition: `/static/city_agri_data.json` now loads through `cityDataPromise` and is included in the initial GeoJSON `Promise.all(...)` before `drawProvinces()`. Previously the map could render before refreshed production-region data arrived.
- Re-ran smoke suite after the fix. Production API endpoints checked: `/health`, `/api/v1/signals/today`, `/api/v1/items/cabbage/forecast`, `/api/v1/items/radish/forecast`, `/api/v1/map/weather` all returned HTTP 200.

# Session 36 - Do not color non-producing regions (2026-07-05 KST)

- User feedback: regions without the selected crop must not be colored as if the crop exists there.
- Fixed province map styling so a region is active/colored only when `CITY_DATA[curItem]` has matching production-region entries for that province prefix.
- Regional price API data alone is no longer enough to color or enable a province. Non-producing regions stay muted grey, do not show the crop hover card, and do not zoom into lower-level crop detail on click.
- Strengthened the crop-region gate: city entries must pass minimum production/area/share/rank checks, and province entries must aggregate to meaningful main-region scale before they receive color, pins, hover cards, or click drill-down.
- Important product rule: map color means "this selected crop has mapped production/main-region data here"; price data may enrich that region, but must not create a crop region by itself.

# Session 35 - Map hover/click popup and period-aware price map (2026-07-05 KST)

- User feedback: lower map levels lost popup behavior after clicking into a region; map colors looked all green; left period buttons did not visibly change map prices.
- Changed the default map mode from production to price so the first view emphasizes crop price/risk signals instead of green production area shading.
- Changed production/price layer priority: when the price layer is enabled, the map uses price mode even if production is also checked.
- Added period-aware forecast calculation with `periodForecastPct(localPct, days)`. Region colors and price pins now use both local regional price deviation and the selected horizon instead of only static production color or a weak global multiplier.
- Added Leaflet click popups through `openRegionPopup(...)`. Province click opens a summary popup after zooming into the lower level; city polygon and city price pin clicks open the same rich region card while also updating the right detail panel.
- Local verification: page loaded without JS console errors; default pins show varied price forecast values such as negative/positive percentages instead of a single green production view; smoke suite passed.

# Session 34 - Map-first UI restore and layer control repair (2026-07-05 KST)

- User feedback: the simplified dashboard removed too much of the core product value. The desired product is map-first: left/top controls for crop, period, and map filters; center map with crop/price/market/climate signals; right detail panel with forecast, chart, reason analysis, period analysis, and crop context tabs.
- Restored `index.html` to the previous map-first FARM MAP dashboard baseline from commit `db4a1dd`, then kept the newer backend/API/model work intact.
- Deployed commit `be90b56` to restore the production dashboard at `https://mk-map.com` with Leaflet map, left filters, price pins, period controls, right detail tabs, and bottom timeline.
- Fixed a layer-control bug where clicking the text label such as `도매시장 위치` did not toggle the checkbox. The layer rows now use clickable row containers plus `toggleLayerRow(event, layer)` and `handleLayer(...)`.
- Local browser verification: `도매시장 위치` toggles from unchecked to checked, marker icons increased from 4 to 12, `2개월` period button becomes active, console errors were empty.
- Smoke verification: `scripts/run_smoke_suite.py --timeout-seconds 300` passed after the UI repair.
- Next UI work: split the right panel into clearer tabs for exact forecast amount, chart and price movement reason, period/horizon analysis, crop metadata, market signals, and climate/event overlays. Keep the map as the primary experience; do not replace it with a card-only landing/dashboard.
## Session 43 - UI Numeric Source Audit (2026-07-05)

- User requested a full check of all numeric UI data because prior Claude work may have inserted arbitrary values.
- Added the source audit document:
  - `docs/data-audit/07-ui-numeric-source-audit.md`
- Production API spot-checks returned 200:
  - `/api/v1/signals/today`
  - `/api/v1/dashboard/cards`
  - `/api/v1/map/prices?item_code=cabbage`
  - `/api/v1/map/regional-prices?item_code=cabbage`
  - `/api/v1/map/weather`
  - `/api/v1/drought`
- Frontend fixes in `index.html`:
  - Header weather no longer shows hardcoded sunny/mock text. It now summarizes `/api/v1/map/weather` or shows unavailable.
  - Inline `CITY_DATA` fallback is cleared before static city data loads, and cleared entirely if `/static/city_agri_data.json` fails. This prevents old hardcoded city numbers from leaking into the map.
  - Dashboard/default briefing no longer uses `ITEMS.risk_score` or `ITEMS.up_prob` fallback numbers. Missing API values render as `—`/collection state.
  - Detail confidence no longer uses arbitrary period-based percentage. It now uses API confidence labels.
  - Retail fallback multiplier `wholesale * 1.35` was removed. Missing regional retail data is hidden instead of estimated.
  - Missing forecast probability no longer defaults to fake `0.5`; neutral/no-value display is used.
- Remaining weak-source items:
  - city-level production/harvest/rank values still depend on static KOSIS-based `city_agri_data.json`; replace with DB-backed `/api/v1/map/production`.
  - market influence by region is still static/reference-like; compute from agromarket origin/market flow.
  - import/substitute supply, pest/soil/FarmMap features, and fine-grained city weather need new collectors or validation before showing numbers.

## Session 44 - Forecast Panel Density And Risk Placement (2026-07-05)

- User feedback: the horizon price amount cells in the price forecast pane were too large, and crop/market risk signals should be visible inside the price forecast context.
- Updated `index.html`:
  - Compacted `.fm-forecast-row` and `.fm-fc-cell` styles: smaller padding, tighter value typography, no inline grid override.
  - Added a `가격 변동 리스크` block directly under the horizon price cells in the forecast pane.
  - Reused the same risk calculation/rendered HTML for both the forecast pane and the `재배·시장` tab, so risk values do not drift between sections.
- Verification:
  - Browser static check confirmed compact grid CSS (`grid`, 3 columns, 11px values, 5px/6px padding), risk block present, and no console errors.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.

## Session 45 - City-Level Map Hover Repair (2026-07-05)

- User reported that after drilling into a region/city map level, moving the mouse over the area still did not show the hover card.
- Updated `index.html` city-level map event handling:
  - City polygon layers now bind `mouseover`, `mouseenter`, `pointerover`, and `pointerenter`, plus matching move/leave events.
  - Added `bindPathDomEvents()` to attach hover/move/leave handlers directly to the underlying SVG path. This is a fallback when Leaflet's event delegation is unreliable after zoom/drill transitions.
  - City label markers also get Leaflet-level hover handlers in addition to the existing DOM marker handlers.
- Verification:
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - Static browser load reported no console errors.

## Session 46 - City Hover Root Fix And Forecast/Market Rebalance (2026-07-05)

- User clarified that the map hover popup still did not appear inside drilled-in regional maps, and that the price forecast period amounts still occupied too much space.
- Root issue addressed:
  - Map was initialized with `preferCanvas:true`, so polygons could render on canvas rather than SVG paths. Previous SVG DOM hover fallback could not reliably work there.
  - Changed map init to `preferCanvas:false` and added `mapVectorRenderer=L.svg({padding:0.5})`.
  - Province and city `L.geoJSON` layers now use `renderer:mapVectorRenderer`.
  - City hover now shows `makeHoverCard()` even for no-data city areas, so hovering does not silently do nothing.
- UI rebalance:
  - Forecast horizon amounts changed from button/card-like blocks to a compact 6-column label strip.
  - Price risk remains in the forecast pane.
  - `재배·시장` pane now focuses on cultivation stats and shipment/market data; duplicate risk panel removed from that tab.
- Verification:
  - Static browser check: 6-column compact strip, no stats risk bars, SVG renderer/preferCanvas false present, no console errors.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.

## Session 47 - Regional Market Basis And Launch Readiness Sweep (2026-07-05)

- User requested that each selected region clearly show which wholesale market basis is used, and asked for a sweep toward a real public/member-ready release rather than an MVP-only screen.
- Updated `index.html`:
  - Price forecast detail now has `rp-market-basis`, showing the selected region label, the market names used, the basis date when available, and whether the market basis is `실측` or fallback `대표`.
  - `/api/v1/map/regional-prices.markets` rows are grouped by `sido` and attached to each regional price context as `market_names`, `market_count`, and `market_base_date`.
  - If real market rows exist for the region, the UI shows those market names. If not, it falls back to the representative regional influence market and labels it as `대표` so it is not mistaken for measured data.
  - Non-functional pest and soil map layer rows are disabled and marked `BETA` instead of appearing as working controls.
  - The unused notification bell is hidden until a real notification/subscription feature is wired.
- Updated `backend/app/routers/maps.py`:
  - Removed the arbitrary retail-price estimate `wholesale * 1.35`.
  - Regional retail values now appear only when observed retail data exists; otherwise `retail` is `null` and `retail_source` is `unavailable`.
- Added `docs/PRODUCTION_READINESS_AUDIT.md` for the next operator/agent:
  - separates currently launchable items from public-launch blockers.
  - records member/auth readiness, data-source readiness, disabled beta features, and remaining compliance/ops work.
- Verification:
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - Static browser check found `rp-market-basis`, disabled beta layer rows, hidden notification button, compact forecast horizon labels, and no console errors.
- Important remaining blockers before broad public marketing:
  - General member registration/login exists and can be used, but farmer/trader role signup still depends on real phone/SMS verification setup.
  - Privacy policy, terms, consent text, and deletion/export policy still need final production copy and links.
  - Import/substitute supply, soil/FarmMap, and pest map overlays remain beta or unconnected.
  - KMA/API collectors should be monitored after each deploy because external provider failures can still reduce feature completeness.

## Session 48 - CI Failure Repair After Launch Sweep (2026-07-05)

- After pushing Session 47, GitHub Actions still failed on the latest `main` commit even though local smoke tests and production deploy checks passed.
- Root cause:
  - CI runs backend tests against SQLite `test_agri.db`.
  - `Forecast` now requires `horizon_days`, `direction`, and `up_probability`, but SQLite initialization only ran `create_all`; the compatibility migration lived inside the PostgreSQL-only block.
  - Existing SQLite test DB schemas could therefore miss `forecasts.horizon_days`, causing API tests to fail with `sqlite3.OperationalError: no such column: forecasts.horizon_days`.
- Fix:
  - Added SQLite-safe schema repair in `backend/app/database.py` immediately after `Base.metadata.create_all`.
  - It checks columns with `PRAGMA table_info`, adds missing forecast/user columns, backfills `direction/up_probability`, removes duplicate forecast rows by `(item_code, base_date, horizon_days)`, and creates the horizon-aware unique index.
- Additional API contract fixes:
  - File-backed horizon explanation responses now include `model.confidence_reason`, `model.confidence_factors`, and `data_freshness`, matching the DB-backed explanation schema.
  - Dashboard cards now calculate 30-day price changes across available `DailyPrice` sources instead of hard-filtering to `source == "kamis"`, so test/imported/expanded collectors can participate.
- Verification:
  - Reproduced the GitHub Actions commands locally under `backend/`.
  - `python -m pytest tests/test_pipeline.py -v --tb=short` passed: 15 passed.
  - `python -m pytest tests/test_api.py -v --tb=short` passed: 30 passed.

## Session 49 - FarmMap Spatial Crop Integration Foundation (2026-07-05)

- User asked whether FarmMap regional map data can be added crop-by-crop, then requested sequential implementation.
- Confirmed product direction:
  - FarmMap SHP/spatial files should become a crop-region layer and prediction feature source.
  - Raw parcel geometry should not be sent directly to the browser; aggregate/simplify first.
- Added storage models:
  - `backend/app/models/farmmap.py`
  - `FarmMapSourceFile`: audit record for downloaded FarmMap source files.
  - `FarmMapCropRegion`: normalized `item_code + sido + sigungu` summaries with area, farm count, source file, year, and confidence.
- Added crop alias mapping:
  - `config/farmmap_crop_aliases.json`
  - Covers current MVP crops: cabbage, radish, onion, green_onion, garlic.
  - Includes seasonal/subtype names such as 고랭지배추, 월동무, 조생양파, 한지형마늘.
- Added source audit tooling:
  - `scripts/audit_farmmap_spatial_file.py`
  - Audits downloaded CSV/GeoJSON/ZIP sources.
  - Detects crop/area/region candidate fields and current item alias hits.
  - SHP ZIPs are detected but currently require conversion to CSV/GeoJSON or adding pyshp/GDAL.
- Added region summary builder:
  - `scripts/build_farmmap_crop_region_summary.py`
  - Converts audited CSV/GeoJSON into normalized FarmMap crop-region summary JSON.
  - Supports explicit field mapping for crop, area, sido, sigungu, region code, source year, and area unit.
- Added backend map endpoint:
  - `/api/v1/map/farmmap/crop-regions?item_code=cabbage`
  - Returns `available:false` until FarmMap files are imported.
  - When data exists, returns aggregated FarmMap region summaries only, not raw parcel geometry.
- Added planning doc:
  - `docs/FARMMAP_INTEGRATION_PLAN.md`
- Verification:
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - Backend API tests passed: 31 passed, including new FarmMap endpoint contract.
  - Sample CSV conversion matched cabbage/onion/radish aliases and produced crop-region summary rows.
- Next work:
  - Download one official FarmMap SHP/CSV source, preferably a province with known cabbage/radish regions.
  - Convert SHP to GeoJSON/CSV with QGIS/GDAL or add pyshp support to parse DBF fields directly.
  - Run `scripts/audit_farmmap_spatial_file.py --input <file>`.
  - Run `scripts/build_farmmap_crop_region_summary.py` with confirmed field names.
  - Add DB import from summary JSON into `farmmap_crop_regions`.

## Session 50 - FarmMap Summary DB Import Path (2026-07-05)

- Continued the FarmMap sequence after the foundation work.
- Added local/batch importer:
  - `scripts/import_farmmap_crop_region_summary.py`
  - Reads summary JSON from `scripts/build_farmmap_crop_region_summary.py`.
  - Calls `init_db()`, records the source file in `farmmap_source_files`, and inserts normalized rows into `farmmap_crop_regions`.
  - Supports `--replace-source` to safely re-import the same FarmMap source file while validating mappings.
- Added admin import API:
  - `POST /admin/import/farmmap/crop-regions`
  - Protected by `X-Admin-Key`.
  - Accepts the same summary JSON shape plus `replace_source`.
  - Deletes existing rows for the same `source_file` by default to avoid duplicate import collisions.
- Verification:
  - Built a sample CSV summary with cabbage/onion/radish aliases.
  - Imported it into a temporary SQLite DB.
  - Queried `get_farmmap_crop_regions("cabbage")` and confirmed `available:true`, 1 region, 1.0 ha, source crop `고랭지배추`.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - Backend API tests passed: 31 passed.
- Next work:
  - Secure one official FarmMap province source file.
  - If it is SHP/DBF, either convert to CSV/GeoJSON or add direct DBF parsing support.
  - Audit actual fields, build summary JSON, import to production through `/admin/import/farmmap/crop-regions`.

## Session 51 - FarmMap DBF/ZIP Direct Audit Support (2026-07-05)

- Continued the FarmMap sequence so official SHP ZIP files can be handled without requiring QGIS/GDAL for the first field audit.
- Added a pure-Python DBF attribute reader to `scripts/audit_farmmap_spatial_file.py`:
  - reads DBF headers, field descriptors, record counts, and sampled records.
  - supports standalone `.dbf`.
  - supports `.zip` archives containing `.dbf`, including typical SHP ZIP bundles.
  - decodes common Korean DBF text encodings using UTF-8, CP949, EUC-KR, then Latin-1 fallback.
- Updated `scripts/build_farmmap_crop_region_summary.py`:
  - accepts `.dbf` directly.
  - accepts `.zip` directly when it contains a `.dbf` attribute table.
  - can build item/region summaries from SHP ZIP attributes when crop/area/region fields are supplied.
- Verification:
  - Generated a temporary DBF ZIP sample with English field names and CP949 Korean values.
  - Built a FarmMap summary directly from the ZIP.
  - Confirmed cabbage/onion/radish alias matching: 고랭지배추, 양파, 월동무.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - Backend API tests passed: 31 passed.
- Important DBF caveat:
  - DBF field names are limited and often ASCII/abbreviated. If an official source has unclear field names, pass explicit `--crop-field`, `--area-field`, `--sido-field`, and `--sigungu-field`.
  - If a provider attached an XLSX column dictionary, use that to map DBF field names before import.

## Session 52 - Official Gangwon FarmMap Download And Land-Use Summary (2026-07-05)

- Continued the FarmMap integration sequence with a real public data.go.kr source.
- Added official source catalog:
  - `config/farmmap_public_sources.json`
  - Gangwon is marked `verified_downloaded`.
  - Other province IDs are marked `candidate_needs_download_verification` so they are not treated as confirmed.
- Added official downloader:
  - `scripts/download_farmmap_source.py`
  - Reads `config/farmmap_public_sources.json`, resolves `publicDataDetailPk`, calls data.go.kr download metadata, and downloads the official ZIP.
- Downloaded the verified Gangwon source locally:
  - data.go.kr page: `https://www.data.go.kr/data/15104490/fileData.do`
  - title: `농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도`
  - file: `농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도_20251231.zip`
  - size: 203,035,902 bytes
  - local path under untracked raw-data storage: `data/farmmap/raw/...zip`
- Strengthened FarmMap ZIP/DBF handling:
  - `scripts/audit_farmmap_spatial_file.py` now samples all DBF files inside a ZIP, not only the first DBF.
  - `scripts/build_farmmap_crop_region_summary.py` now reads all DBFs inside a ZIP when a future crop-name source is available.
  - Korean field hints were repaired from mojibake to stable Unicode escapes.
- Added land-use summary builder:
  - `scripts/build_farmmap_landuse_region_summary.py`
  - Aggregates FarmMap land-use classes by source province/city and area.
- Real Gangwon audit result:
  - ZIP contains 18 city/county SHP/DBF bundles.
  - DBF total records: 736,009.
  - Fields include `CLSF_NM`, `CLSF_CD`, `STDG_ADDR`, `PNU`, `AREA`, `SOURCE_NM`, `FLIGHT_YMD`, `UPDT_YMD`.
  - No crop/item-name field exists in this official Gangwon file.
  - `CLSF_NM` is land-use classification, with values such as `밭`, `논`, `시설`, `과수`, `비경지`; it must not be shown as crop-specific acreage.
- Generated local summary:
  - `data/farmmap/summaries/gangwon_20251231_landuse_summary.json`
  - 736,009 records -> 89 region/class rows.
  - total area: 104,853.407179 ha.
  - class totals: 밭 67,180.66 ha, 논 30,319.39 ha, 시설 4,501.43 ha, 과수 2,766.52 ha, 비경지 85.41 ha.
- Product/data decision:
  - Use this official FarmMap source as an agricultural land-use/parcel base and regional farming-capacity feature.
  - Do not use it directly as a crop-specific map layer.
  - Crop-specific regions still need KOSIS/main-region metadata, AT/KAMIS market data, crop weather regions, or a FarmMap source that actually includes crop attributes.
- Next work:
  - Verify/download priority province sources in `config/farmmap_public_sources.json`, especially Jeonnam, Jeonbuk, Gyeongbuk, Gyeongnam, Jeju, and Chungbuk.
  - Check whether any province/source variant includes a real crop attribute field.
  - Add a DB model/import path for FarmMap land-use summaries if the UI/model will consume this feature directly.
  - Combine land-use area with existing crop main-region metadata to create a sourced regional crop-capacity feature.

## Session 53 - FarmMap Source Expansion: Jeju And Chungbuk (2026-07-05)

- User requested continued sequential progress.
- Verified metadata for all configured FarmMap public-source candidates in `config/farmmap_public_sources.json`.
- Updated `config/farmmap_public_sources.json`:
  - added `detail_pk` for Jeonnam, Jeju, Jeonbuk, Gyeongbuk, Gyeongnam, Gyeonggi, and Chungbuk.
  - added verified content lengths for each source.
  - marked Gangwon, Jeju, and Chungbuk as `verified_downloaded_landuse_only`.
  - marked the remaining provinces as `verified_metadata_needs_download_audit`.
- Downloaded and audited two additional priority sources:
  - Jeju: `농림수산식품교육문화정보원_팜맵공간정보_제주특별자치도_20251231.zip`
    - data.go.kr ID `15104491`
    - size 102,333,467 bytes
    - 2 SHP/DBF bundles
    - 289,379 DBF records
    - land-use summary: 9 region/class rows, 60,352.325070 ha
  - Chungbuk: `농림수산식품교육문화정보원_팜맵공간정보_충청북도_20251231.zip`
    - data.go.kr ID `15104484`
    - size 222,109,625 bytes
    - 11 SHP/DBF bundles
    - 752,300 DBF records
    - land-use summary: 55 region/class rows, 100,197.927280 ha
- Important repeated finding:
  - Jeju and Chungbuk use the same DBF structure as Gangwon.
  - Fields include `CLSF_NM`, `CLSF_CD`, `STDG_ADDR`, `PNU`, `AREA`, `SOURCE_NM`, `FLIGHT_YMD`, and `UPDT_YMD`.
  - No direct crop/item-name field exists.
  - `CLSF_NM` is land-use classification (`밭`, `논`, `시설`, `과수`, `비경지`), not a crop name.
- Generated local untracked outputs:
  - `data/farmmap/audits/jeju_20251231_audit.json`
  - `data/farmmap/audits/chungbuk_20251231_audit.json`
  - `data/farmmap/summaries/jeju_20251231_landuse_summary.json`
  - `data/farmmap/summaries/chungbuk_20251231_landuse_summary.json`
- Product/data decision strengthened:
  - The official province FarmMap sources are not crop-specific layers.
  - Use them as land-use/parcel/cultivation-capacity features.
  - Keep crop-specific coloring and crop-specific production claims sourced from KOSIS/main production-region data, crop-weather-region metadata, market shipment/origin data, or any future source that actually includes crop attributes.
- Next work:
  - Add persistent storage/import/API for `farmmap_landuse_regions`.
  - Join land-use area with existing crop main-region metadata to produce a source-labeled regional crop-capacity score.
  - Continue downloading/auditing Jeonnam, Jeonbuk, Gyeongbuk, Gyeongnam, and Gyeonggi when disk/time budget allows.

## Session 54 - FarmMap Land-Use DB And API Path (2026-07-05)

- Continued without waiting for user confirmation.
- Added persistent backend storage for verified FarmMap land-use summaries:
  - model/table: `FarmMapLanduseRegion` / `farmmap_landuse_regions`
  - unique key: `sido + sigungu + landuse_class + source_file`
  - separate from `FarmMapCropRegion` to prevent land-use area being mistaken for crop-specific area.
- Added local importer:
  - `scripts/import_farmmap_landuse_region_summary.py`
  - accepts summary JSON from `scripts/build_farmmap_landuse_region_summary.py`
  - supports `--replace-source`
  - fixed relative path handling so `data/...` paths are resolved from repo root even after the script switches into `backend/`.
- Also fixed the same relative path issue in:
  - `scripts/import_farmmap_crop_region_summary.py`
- Added admin import API:
  - `POST /admin/import/farmmap/landuse-regions`
  - protected by `X-Admin-Key`
  - imports the same land-use summary JSON shape into Railway DB.
- Added public map API:
  - `GET /api/v1/map/farmmap/landuse-regions`
  - optional filters: `sido`, `landuse_class`
  - returns `source_type: landuse_only`, totals, class totals, area share, and per-region rows.
- Added API contract test:
  - `test_farmmap_landuse_regions_contract`
  - inserts a sample Jeju land-use row and verifies public API totals/class totals.
- Verification:
  - Temporary SQLite import test succeeded with Jeju summary:
    - saved 9 rows
    - total area 60,352.325070 ha
    - top row: 제주특별자치도 / 제주시 / 밭 / 23,664.155 ha
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - `python -m pytest tests/test_api.py -v --tb=short` passed: 32 passed.
- Next work:
  - Import Gangwon, Jeju, and Chungbuk land-use summaries into production after deploy.
  - Wire `/api/v1/map/farmmap/landuse-regions` into the map as a source-labeled land-use/capacity overlay, not a crop acreage layer.
  - Build a crop-capacity score by joining crop main-region metadata with FarmMap land-use area and shipment/market origin data.

## Session 55 - Production FarmMap Land-Use Import (2026-07-05)

- After commit `4ca4061` deployed, verified the production endpoint:
  - `GET https://mk-map.com/api/v1/map/farmmap/landuse-regions`
  - initial response was `available:false`, confirming the API was live but empty.
- Imported local land-use summaries into production through:
  - `POST https://mk-map.com/admin/import/farmmap/landuse-regions`
  - protected with `X-Admin-Key`
- Imported production rows:
  - Gangwon: 89 rows
  - Jeju: 9 rows
  - Chungbuk: 55 rows
- Production verification:
  - all imported rows: 153 region/class rows, 265,403.6595 ha, 1,777,688 parcels
  - Gangwon: 89 rows, 104,853.4072 ha, 736,009 parcels
  - Jeju: 9 rows, 60,352.3251 ha, 289,379 parcels
  - Chungbuk: 55 rows, 100,197.9273 ha, 752,300 parcels
- Encoding note:
  - PowerShell `Invoke-RestMethod | ConvertTo-Json` displayed Korean response text as mojibake, but Python UTF-8 verification confirmed production DB/API values are stored and returned correctly.
- Next work:
  - Add a frontend map layer toggle for FarmMap land-use/capacity.
  - Label it explicitly as `팜맵 농지분류`, not crop acreage.
  - Use land-use totals as a model feature for regional crop-capacity scoring.

## Session 56 - Frontend FarmMap Land-Use Layer (2026-07-05)

- Continued the FarmMap sequence after production import.
- Added a public UI layer toggle in `index.html`:
  - left panel label: `팜맵 농지분류`
  - fetches `GET /api/v1/map/farmmap/landuse-regions`
  - builds province and city summaries in-browser from API rows.
- Map behavior:
  - when the layer is enabled, imported FarmMap provinces/cities are colored by dominant land-use class and area intensity.
  - currently verified source coverage is Gangwon, Chungbuk, and Jeju only.
  - non-imported regions remain normal/neutral; the layer must not imply crop-specific production area.
- Hover/detail behavior:
  - FarmMap hover cards show official land-use area, parcel count, dominant class, and class chips.
  - right detail panel now includes `팜맵 농지분류` under the cultivation/market stats area.
  - detail copy explicitly says `작물별 면적 아님`.
- Verification:
  - local smoke suite passed: `python scripts/run_smoke_suite.py --timeout-seconds 300`.
  - local API after import returned `available:true`, 153 rows, 265,403.6595 ha, `source_type: landuse_only`.
  - browser verification on `http://127.0.0.1:8001/`:
    - page loaded with the new toggle.
    - toggling `팜맵 농지분류` activated the layer and recolored imported regions.
    - clicking a FarmMap-colored city opened the right detail panel and displayed official FarmMap data, e.g. Chuncheon `6,025 ha`, `65,763` parcels, dominant class `밭`.
- Local-only verification data:
  - imported the existing untracked summary JSON files into the local SQLite DB for UI testing.
  - production DB had already been imported in Session 55.
- Next work:
  - deploy this frontend layer to production.
  - after deploy, verify `https://mk-map.com` toggles the layer against the already-imported production FarmMap data.
  - add a model-side `crop_capacity_score` that joins crop main-region metadata with FarmMap land-use area, while keeping the UI label source-safe.
  - consider downloading/auditing Jeonnam, Jeonbuk, Gyeongbuk, Gyeongnam, and Gyeonggi FarmMap sources for broader land-use coverage.

## Session 57 - FarmMap Frontend Deploy Verification (2026-07-05)

- Committed and pushed frontend layer work:
  - commit `ed91b25 Add FarmMap landuse frontend layer`
  - branch `main`
- GitHub Actions:
  - run `28737421210`
  - status completed successfully.
- Production verification:
  - `https://mk-map.com/` HTML contains `팜맵 농지분류`, confirming the deployed frontend includes the new layer toggle.
  - `https://mk-map.com/api/v1/map/farmmap/landuse-regions` returns `available:true`, 153 rows, 265,403.6595 ha, `source_type: landuse_only`.
- Browser caveat:
  - Codex in-app browser still reported `ERR_TOO_MANY_REDIRECTS` and referenced the old `mkmapcom.wordpress.com` failed URL even after opening a new tab.
  - Shell/HTTP checks show the production server itself returns 200, so this appears to be stale browser/site-data behavior in the in-app browser, not a server redirect loop.
- Next work:
  - Use a normal browser or cleared-profile browser to visually verify `https://mk-map.com` after deployment.
  - Continue with `crop_capacity_score` feature generation from FarmMap land-use plus crop main-region metadata.

## Session 58 - FarmMap Crop Capacity Score API And UI Hook (2026-07-05)

- Continued from the FarmMap land-use layer into model-support features.
- Added backend endpoint:
  - `GET /api/v1/map/farmmap/crop-capacity?item_code=cabbage`
  - source type: `crop_metadata_plus_farmmap_landuse`
  - combines `map_viewer/static/city_agri_data.json` crop-region metadata with imported `farmmap_landuse_regions`.
- Score semantics:
  - `capacity_score` is a regional crop support/capacity signal.
  - It is not a price forecast.
  - It is not FarmMap crop acreage.
  - crop metadata supplies crop relevance; official FarmMap land-use supplies agricultural land context.
- Matching rules:
  - `sigungu`: exact `sido_full + sigungu` FarmMap match, confidence `high`.
  - `province`: province-level FarmMap fallback, confidence `medium`.
  - no FarmMap match: crop metadata only, confidence `crop_only`.
- UI update:
  - right detail panel FarmMap section now has `재배 기반 점수`.
  - if the clicked FarmMap city has no crop metadata for the selected item, UI explains: `작물 주산지 메타 없음 / FarmMap 공식 농지분류만 표시 중`.
- Verification:
  - `python -m pytest tests/test_api.py::test_farmmap_crop_capacity_contract tests/test_api.py::test_farmmap_landuse_regions_contract -q` passed.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - local browser verification confirmed the FarmMap layer opens the right detail panel and shows the capacity fallback text for a FarmMap-only city.
- CI guard:
  - `scripts/run_smoke_suite.py` now py-compiles `backend/app/routers/maps.py`.
- Next work:
  - deploy and verify the new capacity API in production.
  - feed `capacity_score`, `farmmap_match_level`, and `crop_to_agri_landuse_ratio` into the price training feature table.
  - add a small source tooltip/explanation in the UI so users do not confuse capacity score with price prediction probability.

## Session 59 - FarmMap Capacity Features In Training Tables (2026-07-05)

- Continued after production capacity API deploy verification.
- Added reusable feature helper:
  - `scripts/farmmap_capacity_features.py`
  - reads `map_viewer/static/city_agri_data.json` for crop-region metadata.
  - reads normalized local FarmMap land-use rows from `backend/agri_twin.db` when available.
  - does not trust raw untracked summary JSON as the primary source, because local JSON display can show encoding noise depending on shell/reader.
- Added six static item-level FarmMap priors to both training table builders:
  - `farmmap_capacity_score_norm`
  - `farmmap_capacity_match_ratio`
  - `farmmap_capacity_high_conf_ratio`
  - `farmmap_crop_to_landuse_ratio`
  - `farmmap_agri_landuse_area_norm`
  - `farmmap_missing_flag`
- Applied to:
  - `scripts/build_price_training_table.py`
  - `scripts/build_price_training_table_v2.py`
- Interpretation:
  - current model rows are item/date-level, not region/date-level, so FarmMap features are repeated as item-level production/cultivation-capacity priors.
  - `farmmap_missing_flag` prevents the model from treating missing FarmMap coverage as confirmed zero farmland.
  - exact city matches increase `farmmap_capacity_high_conf_ratio`; province fallback can still contribute to match coverage if added later.
- Local feature sample for cabbage:
  - `farmmap_capacity_score_norm`: `0.382145`
  - `farmmap_capacity_match_ratio`: `0.540465`
  - `farmmap_capacity_high_conf_ratio`: `0.540465`
  - `farmmap_crop_to_landuse_ratio`: `0.319477`
  - `farmmap_agri_landuse_area_norm`: `0.42053`
  - `farmmap_missing_flag`: `0.0`
- Verification:
  - `python -m py_compile scripts/farmmap_capacity_features.py scripts/build_price_training_table.py scripts/build_price_training_table_v2.py scripts/run_smoke_suite.py` passed.
  - `python scripts/build_price_training_table.py --date 2026-07-05 --min-history 7` exported `data/model/price_training_table_20260705.csv` with 1,121 rows and the six FarmMap columns.
  - `python scripts/build_price_training_table_v2.py --date 2026-07-05 --min-history 7 --output-suffix farmmap_check` exported item CSVs plus `data/model/price_training_table_20260705_farmmap_check.csv` with 1,121 rows.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
- Current limits:
  - only Gangwon, Chungbuk, and Jeju FarmMap land-use rows are present in the local normalized DB.
  - many item main regions are outside that coverage, so several items intentionally keep `farmmap_missing_flag=1`.
  - this is still a support prior, not a region-specific model. A future region/date model should join regional prices, regional weather, shipment-share, and FarmMap region rows directly.
- Next work:
  - run full horizon-model training with the new columns and compare backtest metrics against the previous champion.
  - only promote if holdout/backtest accuracy improves or remains stable with better explanation quality.
  - expand FarmMap source coverage for Jeonnam, Jeonbuk, Gyeongbuk, Gyeongnam, Gyeonggi, and Chungnam to reduce missing flags for cabbage/onion/garlic/green onion.

## Session 60 - FarmMap Candidate Model Gate (2026-07-05)

- Trained a full FarmMap-feature candidate from `data/model/price_training_table_20260705.csv`:
  - prefix: `price_horizon_model_20260705_farmmap_candidate`
  - trained horizons: 1, 7, 14, 30, 90, 180
  - skipped horizon: 365, because `target_365d_change` has 0 usable rows in the 2026-07-05 table.
- Target availability:
  - 1d: 1,121 rows
  - 7d: 1,101 rows
  - 14d: 1,076 rows
  - 30d: 1,016 rows
  - 90d: 821 rows
  - 180d: 516 rows
  - 365d: 0 rows
- Robustness audit:
  - `scripts/audit_price_model_robustness.py` completed for 6 horizons.
  - output: `data/model/horizons/price_horizon_model_20260705_farmmap_candidate_robustness.json`
- Quality gate:
  - default gate with `min_backtest_predictions=100` held all 6 horizons because the candidate backtest count is 40.
  - diagnostic gate with `min_backtest_predictions=40` produced:
    - candidate: 1d, 180d
    - conditional: 90d
    - hold: 7d, 14d, 30d
  - important hold reasons:
    - 7d: low test and backtest direction, high temporal risk.
    - 14d: low test direction, medium temporal risk.
    - 30d: low backtest direction, medium temporal risk.
- Champion comparison:
  - compared candidate against `price_horizon_model_20260701_mixed_approved_v3` with `scripts/build_mixed_horizon_model_set.py`.
  - output: `data/model/horizons/price_horizon_model_20260705_farmmap_mixed_checked_approval_report.json`
  - result: all checked horizons stayed on baseline.
  - reason: the FarmMap candidate improved some MAE/backtest values, but failed one or more strict gates for direction accuracy or MAE regression per horizon.
- Decision:
  - do not promote the FarmMap candidate model artifacts yet.
  - keep the FarmMap training columns in code, because they are useful and source-safe.
  - improve data coverage and feature interaction before using FarmMap as an active prediction driver.
- Next work:
  - add wider FarmMap province coverage to reduce missing flags.
  - try region/date-level training once regional price, weather, shipment-share, and FarmMap rows can be joined directly.
  - add a feature contribution audit for the new FarmMap columns so explanations show whether they are helping or simply adding noise.

## Session 61 - FarmMap Feature Contribution Audit (2026-07-05)

- Added `scripts/audit_farmmap_feature_contribution.py`.
- Purpose:
  - checks whether FarmMap feature columns are actually used by trained horizon models.
  - measures recent-row linear contribution size for each FarmMap feature.
  - ranks FarmMap contribution against all model features.
- Added the script to `scripts/run_smoke_suite.py` py-compile targets.
- Ran contribution audit against:
  - features: `data/model/price_training_table_20260705.csv`
  - models: `data/model/horizons`
  - prefix: `price_horizon_model_20260705_farmmap_candidate`
  - output: `data/model/horizons/price_horizon_model_20260705_farmmap_candidate_farmmap_contribution.json`
- Audit result:
  - audited horizons: 1, 7, 14, 30, 90, 180
  - 365d model missing, because 365d target rows were unavailable.
  - FarmMap features were active in all audited horizons.
  - mean FarmMap contribution share across audited horizons: `0.2220334`.
- Key observations:
  - `farmmap_capacity_score_norm` was the strongest FarmMap feature in every audited horizon.
  - 7d, 90d, and 180d showed `farmmap_capacity_score_norm` as the top-ranked or near-top-ranked feature by recent mean absolute contribution.
  - 90d FarmMap contribution share: `0.25528875`.
  - 180d FarmMap contribution share: `0.35926922`.
- Decision:
  - contribution is real, not dead code.
  - do not promote yet, because the candidate model failed champion comparison on direction/MAE gates.
  - next model work should reduce unstable FarmMap influence by adding better regional coverage and region/date joins rather than static item-level priors only.

## Session 62 - Forecast Reason Clarity And Market Basis Labels (2026-07-05)

- Addressed UX issue: period trend analysis could show one factor saying price may rise and another saying price may fall, without a clear conclusion.
- Updated `index.html` trend rendering:
  - reads forecast probability/direction from the correct `forecast` object in `/forecast/explanation`.
  - adds a top decision card before reasons.
  - groups reason cards into `상승 압력`, `하락 압력`, and `확인할 변수`.
  - if the model has no probability/direction and both up/down reasons exist, the UI says the period has mixed pressure and names that stock/import/shipment timing should be watched before taking one-sided conclusion.
- Updated market basis copy:
  - right panel now includes market source note beside the selected price basis.
  - hover card market section explains whether the wholesale value is a measured regional wholesale-market average or representative fallback.
  - retail note says whether regional retail is observed or unavailable instead of implying a multiplier estimate.
- Updated backend explanation headline:
  - if `up_probability_14d` is missing, headline no longer says `정보 없음로`.
  - it now states that probability data is insufficient and that upward/downward pressure should be read separately.
- Verification:
  - `python -m py_compile backend/app/routers/forecasts.py` passed.
  - `cd backend; python -m pytest tests/test_api.py -q` passed: 33 tests.
  - `python scripts/run_smoke_suite.py --timeout-seconds 300` passed.
  - local browser static load had no app runtime errors; API warnings were expected because a static file server does not expose backend `/api` routes.

## Session 63 - Forecast Explanation API Contract (2026-07-05)

- Promoted the trend explanation decision logic from frontend-only behavior into backend API response fields.
- Updated `backend/app/routers/forecasts.py`:
  - `/api/v1/items/{item_code}/forecast/explanation` now returns `pressure_summary`.
  - The same endpoint now returns `reason_groups`, grouped as `상승 압력`, `하락 압력`, and `확인할 변수`.
  - Added top-level compatibility fields: `direction`, `direction_label`, `up_probability_14d`, and `up_probability_label`.
  - Static/no-forecast fallback responses now also return the same `pressure_summary` and `reason_groups` shape.
- Updated `backend/app/services/horizon_forecasts.py`:
  - horizon-file explanation responses now expose the same contract, so active multi-horizon model files do not bypass the UI explanation structure.
  - model explanation rows are converted from contribution sign into up/down/neutral reason cards.
  - mixed pressure is explicitly represented when upward and downward contributions coexist.
- Updated `index.html`:
  - trend panel now prefers `data.pressure_summary` and `data.reason_groups` from the backend.
  - legacy fallback logic remains for older responses.
- Updated `backend/tests/test_api.py`:
  - coverage now asserts `pressure_summary` and `reason_groups` exist.
  - payload test asserts top-level direction/probability compatibility fields.
- Verification:
  - `python -m py_compile backend\app\routers\forecasts.py backend\app\services\horizon_forecasts.py` passed.
  - `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - local backend at `http://127.0.0.1:8017` returned `pressure_summary` and `reason_groups` for cabbage explanation with status 200.
  - browser load of the local app had no captured runtime errors.

## Session 64 - Forecast Explanation Page Contract Alignment (2026-07-05)

- Extended the standalone forecast explanation page at `map_viewer/templates/forecast_explanation.html` to consume the same API contract as the main map UI.
- Added a visible decision card above the reason list:
  - title/body come from `pressure_summary`.
  - backend color/background hints are applied when present.
- Reworked the reason section:
  - prefers backend `reason_groups`.
  - falls back to grouping legacy `reasons` into `상승 압력`, `하락 압력`, and `확인할 변수`.
  - reads `message` as well as `description`/`summary`, so horizon model contribution explanations display instead of empty placeholder text.
- Verification:
  - `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - local browser check at `http://127.0.0.1:8017/forecast-explanation?item=cabbage&horizon=14` showed the decision card and grouped 상승/하락 reasons with no captured runtime errors.

## Session 65 - Map Hover And Production Coverage Clarity (2026-07-05)

- Addressed map UX issue where hover cards could fail after drilling from province to city/county level.
- Updated `index.html`:
  - added a map-level hover fallback using `elementFromPoint` for Leaflet SVG paths and marker icons.
  - marker child elements no longer intercept pointer events, so region pins receive hover reliably.
  - tooltip horizontal position is clamped inside the viewport to avoid left/right clipping.
  - no-price fallback now shows `가격 수집 중` instead of calculating and displaying `0원`.
- Clarified production/coverage semantics:
  - right-panel `재배·시장` tab now explains that highlighted city/county areas are representative or currently verified production/shipment metadata, not the only places that produce or ship the crop.
  - same-province confirmed production areas are listed when available.
  - if only one city/county is in current metadata, the UI explicitly says other areas are data-unverified, not non-producing.
  - inactive hover cards now say the area is outside current representative crop metadata, not that there is no production.
- Verification:
  - `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - local browser check drilled into cabbage/Chungbuk/Goesan and verified the lower-level hover card appears, remains inside viewport, and no longer shows `0원` for unavailable price.

## Session 81 - All Mapped Item Model Refresh And Backtest (2026-07-06)

- Processed all currently model-ready crops: cabbage, radish, onion, green_onion, garlic.
- Downloaded fresh KAMIS 730-day price data and Agromarket regional 365-day price data.
- Audited feature coverage:
  - price target and market data are usable,
  - agri weather is usable with backfill,
  - disaster and forecast APIs are currently context/recent signals rather than full historical drivers,
  - production/FarmMap signals remain mostly static annual/regional features.
- Built `data/model/price_training_table_20260706.csv`:
  - 1,121 rows,
  - 91 columns,
  - crop-specific features for cabbage/radish/onion/green_onion/garlic.
- Ran daily model promotion/backtest for 1, 14, 30, 90, and 180 day horizons.
- 365-day horizon was rejected because there were zero valid 365-day target rows.
- The new candidate model was not promoted because it did not consistently beat the existing champion in direction accuracy and MAE.
- Checked artifact:
  - `price_horizon_model_20260706_all_items_checked_no365`
  - strict predictions/explanations generated locally for all 5 mapped crops.
- Local API check:
  - active public horizons: 1, 14, 30, 90,
  - hidden horizon: 180,
  - forecast endpoints returned 200 for all 5 mapped crops.
- Updated `backend/app/services/horizon_forecasts.py` so public horizon explanation text is normal Korean instead of mojibake/encoding-corrupted text.
- Verification:
  - `python -m py_compile backend\app\services\horizon_forecasts.py` passed.
  - `$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q` passed: 38 tests.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - Local FastAPI check returned 200 for all 5 mapped crops with active horizons 1/14/30/90 and hidden horizon 180.
- Detailed handoff:
  - `docs/AI_SESSION_81_ALL_ITEM_MODEL_BACKTEST.md`

Production caution:

- `data/model` and other generated data directories are ignored by Git.
- A code push alone does not upload local model artifacts.
- To apply this exact model output in production, rerun the same pipeline on the server or upload/sync the generated artifacts through the production storage path.

## Session 82 - Candidate Item Expansion To 20 Crops (2026-07-06)

- Added KAMIS candidate audit tooling and draft metadata generation tooling.
- Expanded metadata registry from 5 items to 20 items by adding draft metadata for:
  - apple, carrot, chamoe, cucumber, fresh_pepper, lettuce, pear, pepper, perilla, potato, sesame, spinach, sweet_potato, tomato, watermelon.
- Ran KAMIS 365-day collection for all 20 registry items:
  - all 20 succeeded with no API errors.
- Built 20-item training table:
  - `data/model/price_training_table_20260706.csv`
  - 4,336 rows, 91 columns.
- Trained/backtested 20-item candidate horizons 1/14/30/90/180.
- Candidate model was not promoted:
  - all horizons stayed on the 5-item checked baseline champion because the 20-item candidate failed direction/MAE promotion gates.
  - strict quality held 1/14/30/90 because of `temporal_high_risk`.
  - 180 generated predictions but remains public-hidden by policy.
- Added `--artifact-label` to `scripts/run_daily_model_promotion.py`; future experiments should use a non-daily label to avoid overwriting daily latest files.
- Verification:
  - `$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_horizon_forecasts.py backend\tests\test_api.py -q` passed: 38 tests.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Detailed handoff:
  - `docs/AI_SESSION_82_ITEM_EXPANSION_20.md`

Production caution:

- The 15 new metadata items are draft/model-candidate items, not public production-approved forecast items.
- They have KAMIS price data, but KMA/KOSIS/FarmMap/Agromarket context still needs verification before public prediction confidence is acceptable.

## Session 97 - Cultivation And Market Panel Cleanup (2026-07-06)

- Cleaned the right-panel `재배·시장` tab in `index.html`.
- Removed duplicate `rp-coverage-note` / `rp-neighbor-note` render blocks that repeatedly showed coverage caveats.
- Added a judgment-first sentence above the market cards so the panel says how to interpret the selected region before showing numeric cards.
- Kept the useful cards:
  - national shipment rank,
  - national share,
  - province share,
  - price influence judgment,
  - same-province shipment ranking,
  - monthly shipment concentration,
  - basis market/current price.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Browser note:
  - local page loaded through `http://127.0.0.1:8765`,
  - current browser wrapper limited automated map/detail click verification,
  - follow-up should manually or fully Playwright-check the detail panel after deploy.
- Detailed handoff:
  - `docs/AI_SESSION_97_MARKET_PANEL_CLEANUP.md`

## Session 98 - Risk Judgment Copy Cleanup (2026-07-06)

- Cleaned the `가격 예측` tab's `가격 변동 리스크` section in `index.html`.
- Increased the risk explanation area from tiny 9px inline text to readable 13px text.
- Removed duplicate risk rendering code in `showRegionDetail`.
- Removed duplicate definitions of `riskLevelInfo`, `buildRiskBreakdown`, and `riskBarsHtml`.
- Strengthened risk copy so it now explains the current state:
  - weather/disaster score explains harvest/logistics delay pressure,
  - shipment/growth score explains supply shortage or stability pressure,
  - market/price score explains regional price stress or normality.
- The total risk summary now identifies the strongest cause and mentions low-scoring factors that reduce the overall risk.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - `rg` confirmed only one canonical risk function set remains.
- Detailed handoff:
  - `docs/AI_SESSION_98_RISK_JUDGMENT_COPY.md`

## Session 99 - Trend Signal Compaction (2026-07-06)

- Cleaned `가격 예측 > 기간별 가격 동향 분석` in `index.html`.
- Added a frontend compaction layer for repeated trend reasons:
  - direction,
  - category,
  - label.
- Similar or duplicate reasons are now merged into one item with an `n개 묶음` badge.
- Added compact icon summaries before the detailed reason cards.
- Category icons cover:
  - weather/disaster,
  - shipment/growth/supply,
  - stock/storage,
  - import/substitute supply,
  - market/price.
- This reduces the mechanical "상승 압력" list feeling, especially for cabbage-like cases with many same-direction signals.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Detailed handoff:
  - `docs/AI_SESSION_99_TREND_SIGNAL_COMPACTION.md`

## Session 100 - Dashboard Statistics Panel (2026-07-06)

- Expanded the top `통계` navigation view in `index.html`.
- Added a judgment-first dashboard with:
  - today's priority crop,
  - price data count,
  - caution item count,
  - forecast-ready item count,
  - shipment metadata count.
- Added rank sections:
  - today's priority,
  - upward pressure,
  - downward pressure,
  - price anomaly,
  - risk score,
  - rise/fall probability signal,
  - shipment scale,
  - production concentration,
  - forecast data readiness.
- Added derived dashboard metrics:
  - priority score,
  - max regional price gap,
  - top shipment region,
  - production concentration,
  - 4-week/3-month forecast change.
- Hardened empty-data behavior:
  - rows without usable data are not forced into rankings,
  - empty sections display `아직 비교 가능한 데이터가 없습니다.`,
  - top judgment no longer shows misleading `우선점수 0점입니다`,
  - awkward Korean particle output such as `배추은` was fixed with `topicName`.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
  - local browser check confirmed the dashboard opens and empty-data fallback behaves correctly.
- Detailed handoff:
  - `docs/AI_SESSION_100_DASHBOARD_STATS_PANEL.md`

## Session 101 - Weather Layer Visibility (2026-07-06)

- Improved the map `기상 정보` layer in `index.html`.
- Removed the duplicate earlier `loadWeatherLayer` / `removeWeatherLayer` definitions.
- Added a canonical weather layer flow:
  - `weatherRegionPosition`,
  - `weatherState`,
  - `weatherSummary`,
  - `loadWeatherLayer`,
  - `removeWeatherLayer`.
- Weather markers are now larger badge-style overlays that show:
  - icon,
  - region short name,
  - average temperature,
  - temperature anomaly.
- Weather states now include judgment text for:
  - heavy rain,
  - cold wave / low temperature,
  - heat wave / high temperature,
  - normal weather.
- Tooltips now explain how the weather state can affect harvest, logistics, crop quality, or price pressure.
- The bottom-left map legend now shows a compact weather judgment summary rather than a generic API explanation.
- The left sidebar copy now explains how to interpret weather badges over the price-color map.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Detailed handoff:
  - `docs/AI_SESSION_101_WEATHER_LAYER_VISIBILITY.md`

## Session 102 - Weather Detail Judgment (2026-07-06)

- Connected weather data to the right-side `가격 예측` detail panel in `index.html`.
- Added the `rp-weather-judgment` card under the current price/market basis area.
- Added shared weather cache:
  - `LIVE_WEATHER_MAP`,
  - `LIVE_WEATHER_BY_REGION`,
  - `fetchWeatherMapData`.
- `updateHeaderWeather` and `loadWeatherLayer` now share the same weather API cache.
- Added selected-region weather interpretation helpers:
  - `weatherForDetailRegion`,
  - `weatherRegionLabel`,
  - `weatherPositionForRegion`,
  - `regionWeatherPriceJudgment`,
  - `renderRegionWeatherJudgment`.
- The selected region panel now shows:
  - weather state,
  - temperature,
  - temperature anomaly,
  - precipitation,
  - humidity,
  - a crop/price judgment sentence.
- Weather judgment considers shipment YoY and harvest rate so it can say whether bad weather is likely to increase price pressure, delay shipment, or remain limited.
- Important production compatibility:
  - `/api/v1/map/weather` can return rows like `kma_cabbage` rather than province codes,
  - detail panel matching falls back to `kma_${curItem}`,
  - map weather markers place crop-weather rows near that crop's representative production province.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Detailed handoff:
  - `docs/AI_SESSION_102_WEATHER_DETAIL_JUDGMENT.md`

## Session 103 - Map Hover Title Fallback (2026-07-06)

- Addressed persistent map hover popup failures in `index.html`.
- Production inspection showed:
  - `.leaflet-interactive` SVG paths had title text,
  - `data-fm-dom-bound="1"` was present,
  - but the rich tooltip handler was not reliably available.
- Added title/data-tooltip based fallback helpers:
  - `mapFallbackTitle`,
  - `mapFallbackTooltipHtml`,
  - `fallbackTooltipHandlersFor`.
- `findHoverTargetAtPoint` now accepts title-only SVG/marker targets.
- `setupMapHoverFallback` now uses rich handlers when available, otherwise builds a simple custom popup from the element title.
- Verification:
  - `git diff --check` passed.
  - `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Detailed handoff:
  - `docs/AI_SESSION_103_MAP_HOVER_TITLE_FALLBACK.md`
