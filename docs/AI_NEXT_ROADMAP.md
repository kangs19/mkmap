# MK-MAP Next Roadmap

마지막 업데이트: 2026-07-01 KST (세션6)

## P0: 운영 DB에 예측/신호 반영

현재 가장 중요하다.

문제:

- 코드 배포는 됐다.
- 공개 API 날짜 기준도 KST로 바뀌었다.
- 하지만 운영 DB에 `region_signals`, `forecasts`가 비어 있다.

해야 할 일:

1. Railway Variables 확인
   - `DATABASE_URL`
   - `ADMIN_KEY`
   - `DATA_GO_KR_API_KEY` (없으면 AT 소스 skip되고 KAMIS만 수집 — 수정됨)
   - `KAMIS_API_KEY`
   - `KOSIS_API_KEY`

현재 상태:

- 로컬 `.env`에는 API 키, `ADMIN_KEY`, endpoint/operation 기본 설정이 채워져 있다.
- 로컬 라이브 진단 기준 `missing_env`는 0이다.
- `KOSIS_PRODUCTION_TBL_ID`는 의도적으로 비워둔다. 품목별 통계표 ID는 메타데이터에서 읽는다.
- `https://mk-map.com/api/v1/admin/status`는 로컬 `ADMIN_KEY` 헤더로 호출 시 503을 반환했다.
- Railway에 `ADMIN_KEY`와 `DATA_GO_KR_API_KEY`가 없었다.

완료된 수정:
- **Dockerfile**: `scripts/`, `mkmap_meta/`, `config/` COPY 누락 수정 (커밋 83c1b3b)
- **collect_live_price_features.py**: env 전체 일괄 체크 대신 서비스별 개별 체크로 변경 → `DATA_GO_KR_API_KEY` 없어도 KAMIS 수집 가능 (커밋 007c306)

완료된 수정 (세션3):
- collect_live_weather_features: TimeoutError 캐치 추가 (커밋 ecd6994)
- run_meta_pipeline: 날씨/모델/예측 단계 soft_fail 적용 (커밋 ecd6994)
- build_price_training_table: min_required_history 28→14 (커밋 ecd6994)
- 로컬 파이프라인 전체 성공 확인: signals 85행, forecasts 5개 import 완료

완료된 수정 (세션4):
- scripts/push_outputs_to_server.py 추가 — 로컬 생성 JSON을 Railway에 HTTP POST (커밋 3d88171)
- admin import-outputs 엔드포인트 추가 (커밋 3d88171)
- pipeline status step-level summary 추가 (커밋 41b20c6)
- start.sh APP_ENV 기본값 production 설정 (커밋 85049a6)

**남은 P0 차단 요소 (사용자 직접 필요)**:
- Railway Variables에 다음 키 추가/수정:
  - `KAMIS_API_KEY`
  - `DATA_GO_KR_API_KEY`
  - `KOSIS_API_KEY`
  - `KMA_API_KEY`
  - `ADMIN_KEY`
  - `APP_ENV` = `production` (현재 Railway에 `development`로 설정되어 있거나 없는 경우, `/health`가 `"env":"development"` 반환 중 — 2026-07-01 확인)
- 값은 `C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git\.env` 참조
- Railway Variables 추가 후 재배포하면 auto-recover가 자동으로 파이프라인 실행

2. Admin status 확인

```powershell
$headers = @{ "X-Admin-Key" = "<ADMIN_KEY>" }
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/status" -Headers $headers
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/meta-pipeline/status" -Headers $headers
```

3. 원격 pipeline 실행

```powershell
$headers = @{ "X-Admin-Key" = "<ADMIN_KEY>" }
Invoke-RestMethod `
  -Method Post `
  -Uri "https://mk-map.com/api/v1/admin/meta-pipeline/run?background=false&weather_lookback_days=3&weather_max_requests_per_item=16&weather_request_timeout_seconds=8" `
  -Headers $headers
```

4. 공개 API 재확인

```powershell
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/signals/today"
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/items/cabbage/forecast"
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/dashboard/cards"
```

성공 기준:

- `signals/today.items`에 5개 품목이 나온다.
- `items/cabbage/forecast`가 200으로 예측을 반환한다.
- dashboard cards에 forecast/risk/price 값이 null이 아니게 된다.

## P0: 원격 pipeline 실패 로그 확보

원격 pipeline이 실패하면 admin status의 `last_output_tail`을 확인한다.

가능한 실패 원인:

- Railway에 API 키 누락
- `ADMIN_KEY` 누락
- `DATABASE_URL`이 다른 DB를 바라봄
- KMA weather gateway timeout
- provider API 오류가 아직 특정 collector에서 예외로 터짐
- Railway 실행 시간이 너무 길어짐

해야 할 보강:

- admin pipeline status에 명령어 전체와 duration 저장
- pipeline 실패 시 어느 step에서 실패했는지 별도 필드 저장
- stdout tail 80줄보다 step summary를 구조화해서 저장

## P1: 운영 pipeline 결과 자동 검증

현재 로컬에서는 검증이 잘 되지만, 운영에서 성공 여부를 사람이 직접 확인해야 한다.

완료됨:

- `scripts/verify_public_api_outputs.py`
  - `/health`
  - `/signals/today`
  - `/dashboard/cards`
  - `/items/{item}/forecast`
  - expected date check
  - empty/null check

실행:

```powershell
python scripts\verify_public_api_outputs.py --expected-date 2026-07-01
```

기본은 진단용이라 데이터가 비어도 exit code 0이다. CI나 배포 gate에서 실패 처리하고 싶으면 `--strict`를 붙인다.

```powershell
python scripts\verify_public_api_outputs.py --strict
```

남은 일:

- admin endpoint:
  - `POST /api/v1/admin/meta-pipeline/verify`
  - 또는 status에 latest public output summary 포함

성공 기준:

- pipeline 실행 후 자동으로 공개 API까지 확인된다.

## P1: 서버 DB import 안정화

현재 import script:

- `scripts/import_meta_outputs_to_backend.py`

해야 할 점검:

- `latest_price_predictions_YYYYMMDD_risk.json`가 5개 품목을 모두 갖는지 검사
- `region_risk_signals.json`가 85행급인지 검사
- import 후 DB row count 검사
- forecasts 5개 미만이면 실패 처리
- region_signals 0이면 실패 처리

필요하면 import script 마지막에 summary를 더 강하게 출력한다.

## P1: RDA 농업기상 활용도 개선

**완료 (세션4, 커밋 0c1efe9)**

완료된 작업:
- 전체 219개 RDA 관측소 코드 목록 확보 (2026-07-01 API live 확인)
- 5개 품목별 주산지 RDA 관측소 매핑 추가 (`metadata/items/*.json` 의 `rda_weather.obsr_spot_codes`)
  - 배추: 강원 고랭지 10개, 전남 겨울 5개, 충남 봄가을 3개 = 18개 관측소
  - 무: 제주 7개, 울산 2개, 부산 1개, 충남 2개 = 12개 관측소
  - 양파: 전남 5개, 경남 2개 = 7개 관측소
  - 대파: 전남 3개, 경북 포항 3개 = 6개 관측소
  - 마늘: 경북 의성 3개, 전남 3개, 충남 1개 = 7개 관측소
- weather.py: `RdaAgriWeatherConnector.fetch_weather` 품목별 관측소 쿼리로 확장
- weather.py: 전월 폴백 추가 (RDA 데이터는 ~1개월 lag 있음)
- weather.py: `_xml_to_payload` root 태그 wrapping 수정 (extract_rows가 파싱 못하던 문제)
- normalizers.py: `public_api_error`가 RDA 성공코드 `"200"`을 오류로 인식하던 버그 수정
- normalizers.py: `obsr_Spot_Cd/Nm` 필드를 region 추출에 추가

실측 결과: 배추 540개, 마늘 210개, 양파 210개, 대파 180개, 무 330개 feature 수집 성공

남은 개선:
- RDA weather feature를 CachedWeatherConnector 기본 source에 포함할지 결정
- 일일 파이프라인에서 RDA 수집 통합 확인

## P1: AT 정산정보 품목 매핑 확장

현재 안전하게 일부 품목만 AT settlement mapping을 활성화했다.

주의:

- 배추/무는 유사 품목명이 많아 broad query로 잘못 매핑하면 안 된다.
- 예: 얼갈이, 양배추, 열무, 자두 후무사 같은 오염 가능성이 있었다.

현재 상태:

- 세션4 기준 AT 정산 API (apis.data.go.kr/B552845/katSale) 502 Bad Gateway 상태
- 배추/무 코드 live 확인 불가
- 기존 캐시 파일(20260701)에는 배추/무 settlement 데이터 없음 (빈 배열)
- 양파/대파/마늘: lclsf "12"(조미채소류) 확인됨
- 배추: lclsf 미확인 (엽채류), 무: lclsf 미확인 (근채류)

해야 할 일:

- AT API 복구 후 `discover_at_codes4.py` 스크립트로 lclsf 코드 확인
- 공식 코드표 또는 실제 endpoint filtered 결과로 정확한 대분류/중분류/소분류 코드 확인
- 배추/무 정산 mapping 추가 (cabbage.json, radish.json에 at_settlement 블록 추가)
- `scripts/test_live_at_market_settlement.py`로 live 확인

성공 기준:

- 배추/무 정산정보가 정확한 품목명으로만 나온다.
- risk signal market pressure에 settlement source가 포함된다.

## P2: 모델 품질 개선

**세션5 일부 완료 (커밋 59c53e8)**

실제 확인된 훈련 데이터 상황:
- KAMIS 캐시: 20개 날짜 (2026-06-02 ~ 2026-06-30), 5개 품목 × 5행 = 25행 (매우 부족)
- AT regional price: region_code="1101" (숫자 코드), "평균" 필터에 걸리지 않아 0행 사용됨
- 훈련 행 25개로 모델이 의미 있는 패턴 학습 불가 (이전 "120행"은 오기)

완료된 수정 (커밋 59c53e8):
- `build_price_training_table.py`:
  - `_daily_retail_series`: KAMIS "평균" 전국 평균 소매가 추출 (기존 로직 개선)
  - `_daily_at_wholesale`: AT regional/settlement 도매가 일별 평균 별도 추출
  - `price_pct_of_hist_mean`: 현재가/역사적평균 - 1 (품목 간 스케일 정규화)
  - `at_wholesale_norm`: AT 도매가/KAMIS 소매가 - 1 (도소매 스프레드 신호)
- `train_price_baseline_model.py`:
  - `EXCLUDED_COLUMNS`에 절대가격 컬럼 추가 (`avg_price`, `lag_*_price`, `ma_*_price`)
  - 크로스 아이템 훈련 시 배추(400원) vs 마늘(5000원) 스케일 혼동 방지
  - 모델이 정규화된 피처만 사용: change_*, ma_*_gap, volatility_*, cyclicals, at_wholesale_norm

**세션6 완료:**
- 365일 가격 수집 완료 — KAMIS 3000~4700건/품목
- 파이프라인 재실행 결과:
  - 훈련 행: **1118행** (기존 25행 → 45배)
  - direction_accuracy: **81.7%** (test), **87.5%** (backtest)
  - confidence: **"high"**
  - garlic/green_onion 품목별 모델 채택
- `train_price_baseline_model.py` numpy 가속 (커밋 4b698c1) — **9초** (기존 30분)
- Codex 클론에 개선된 스크립트 동기화 완료

남은 작업:
- Railway ADMIN_KEY 추가 후 `import_meta_outputs_to_backend.py` 실행으로 운영 DB 반영
- 실제 다음날 가격 확인 후 direction 예측 정확도 검증 (base_date 2026-06-29 예측 → 2026-06-30 실제)
- 외부 위험 신호의 price adjustment scale 검증 (별도 태스크)

## P2: 프론트 UI 실제 데이터 대응

**완료 (세션5, 커밋 b0ef561)**

완료된 작업:
- 데이터 없음 상태 UI — `mc-nodata-notice` 배너, 품목별 위험도 "—" 표시
- 데이터 freshness 표시 — `#data-status-pill` (live/nodata/loading 3상태, base_date KST 표시)
- `showRegionDetail` KST 기준 date 표시 — `LIVE_BASE_DATE` 사용
- null 데이터 레이아웃 깨짐 수정 — price/yoy/chgPct/forecast 모두 null-safe

남은 개선 (낮은 우선순위):
- 우측 패널에 마지막 pipeline 실행 시각/결과 표시 (admin status API 연동)
- forecast explanation 페이지 별도 구현 (현재 없음)

## P2: API 진단 결과 운영 UI 연결

이미 admin status는 latest diagnostic을 노출한다.

더 할 일:

- live diagnostics를 scheduler 후 자동 실행할지 결정
- provider no_data/api_error를 색상/문구로 구분
- KMA satellite HTTP_403 같은 승인 문제는 별도 “권한 확인 필요”로 표시

## P3: 자동화와 운영 알림

**완료 (세션5, 커밋 b35ed7d)**

완료된 작업:
- Discord 성공 알림에 signal_count, forecast_count 포함 (DB에서 직접 쿼리)
- 마지막 로그 3줄 코드블록으로 embed에 포함
- 실패 시 `notify_pipeline_error`로 에러 메시지 전송 (기존 유지)

남은 개선 (선택):
- Railway restart 후 auto-recover 결과를 별도로 Discord 전송
- public verify 결과 (signals/today, items/cabbage/forecast 등) 포함

## 계속 업데이트할 것

작업을 끝낼 때마다 이 파일의 각 항목 상태를 수정한다.

형식:

- 완료됨
- 진행 중
- 보류
- 실패 원인
- 다음 액션
