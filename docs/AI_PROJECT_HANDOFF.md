# MK-MAP Project Handoff

마지막 업데이트: 2026-07-01 KST (세션12)

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

## 다음 우선순위

1. garlic DB 단위 정합: Railway 배포 후 `POST /api/v1/admin/debug/fix-garlic-prices` 호출
2. AT settlement 90일 재수집 (자정 KST 리셋 후) → 로컬 파이프라인 재실행 + push
3. Railway forecasts 자동화 검증 (다음 06:00 KST 이후 확인)

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

## 현재 완성도

코드와 로컬 파이프라인 기준:

- 약 80~82%

운영 서비스까지 포함:

- 약 70~72%

가장 큰 남은 차이는 운영 DB에 실제 pipeline 산출물이 들어가는지 확인하는 것이다.
배추/무 AT settlement 코드 추가로 데이터 정확도가 개선될 예정.
