# MK-MAP Project Handoff

마지막 업데이트: 2026-07-01 KST (세션4)

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

## 지금 가장 먼저 해야 할 일

1. Railway 환경변수 확인
   - `DATABASE_URL`
   - `ADMIN_KEY`
   - `DATA_GO_KR_API_KEY`
   - `KAMIS_API_KEY`
   - `KOSIS_API_KEY`
   - 그 외 `.env.example`에 있는 public API endpoint 변수

2. 원격 admin 상태 확인

```powershell
$headers = @{ "X-Admin-Key" = "<Railway ADMIN_KEY>" }
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/status" -Headers $headers
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/meta-pipeline/status" -Headers $headers
```

3. 원격 pipeline 수동 실행

```powershell
$headers = @{ "X-Admin-Key" = "<Railway ADMIN_KEY>" }
Invoke-RestMethod `
  -Method Post `
  -Uri "https://mk-map.com/api/v1/admin/meta-pipeline/run?background=false&weather_lookback_days=3&weather_max_requests_per_item=16&weather_request_timeout_seconds=8" `
  -Headers $headers
```

4. 실행 후 공개 API 재확인

```powershell
python scripts\verify_public_api_outputs.py --expected-date 2026-07-01
```

현재 스크립트는 기본적으로 진단 결과를 JSON으로 출력하고 exit code 0을 반환한다. 배포 gate처럼 실패 처리해야 할 때는 `--strict`를 붙인다.

## 현재 완성도

코드와 로컬 파이프라인 기준:

- 약 75~80%

운영 서비스까지 포함:

- 약 65~70%

가장 큰 남은 차이는 운영 DB에 실제 pipeline 산출물이 들어가는지 확인하는 것이다.
