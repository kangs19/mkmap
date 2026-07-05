# MK-MAP Workflow And Storage

마지막 업데이트: 2026-07-01 KST

## 저장 원칙

이 프로젝트는 코드, 설정, 원본 데이터, 정규화 feature, 모델 산출물, 백엔드 DB import 결과를 분리한다.

Git에 들어가는 것:

- 코드
- metadata JSON
- schema
- config 템플릿
- 문서
- smoke/test 스크립트

Git에 넣지 않는 것:

- `.env`
- 실제 API 키
- Admin key
- SQLite DB
- `data/` 아래 생성 산출물
- raw API response
- model output

## 주요 디렉터리

### `metadata/`

품목별 메타데이터의 원천이다.

각 품목은 다음 정보를 갖는다.

- item code/name
- weather profile
- event profile
- price mapping
- production mapping
- external mappings
- engine plan

품목을 추가할 때는 이 메타데이터 구조에 맞춰 추가해야 한다.

### `config/`

API 서비스 카탈로그와 외부 매핑 템플릿이 있다.

중요 파일:

- `config/api_services.json`
- `config/external_mappings/kma_crop_weather_template.csv`

### `mkmap_meta/`

메타데이터 기반 feature engine, connector, pipeline이 있다.

중요 영역:

- `connectors/price.py`
- `connectors/weather.py`
- `connectors/events.py`
- `connectors/production.py`
- `connectors/cached.py`
- `engines/risk_signal.py`
- `pipeline.py`
- `factory.py`

### `scripts/`

개별 수집, 진단, 학습, 예측, import를 실행하는 운영 스크립트 모음이다.

핵심 스크립트:

- `run_meta_pipeline.py`
- `run_live_api_diagnostics.py`
- `collect_live_price_features.py`
- `collect_live_weather_features.py`
- `collect_live_event_features.py`
- `collect_live_production_features.py`
- `build_model_dataset.py`
- `export_live_signals.py`
- `build_price_training_table.py`
- `train_price_baseline_model.py`
- `predict_latest_prices.py`
- `import_meta_outputs_to_backend.py`
- `verify_public_api_outputs.py`
- `run_smoke_suite.py`

### `data/`

생성 산출물 저장소다. Git ignore 대상이다.

구조:

```text
data/
  raw/
    YYYYMMDD/
      <source>.json
  features/
    YYYYMMDD/
      kamis_price_<item>.json
      at_regional_price_<item>.json
      at_market_settlement_<item>.json
      kosis_production_<item>.json
      kma_crop_weather_<item>.json
      weather_alert.json
      impact_forecast.json
      typhoon.json
      midterm_forecast.json
      satellite.json
      weather_chart.json
      *_collection_summary.json
  signals/
    YYYYMMDD/
      region_risk_signals.json
  model/
    price_prediction_dataset_YYYYMMDD.csv
    price_training_table_YYYYMMDD.csv
    price_baseline_model_YYYYMMDD.json
    price_baseline_model_YYYYMMDD_evaluation.json
    price_baseline_model_YYYYMMDD_backtest.json
    latest_price_predictions_YYYYMMDD_risk.json
  diagnostics/
    YYYYMMDD/
      live_api_diagnostics.json
```

### `backend/`

FastAPI 서버다.

주요 기능:

- 공개 API
- admin API
- scheduler
- backend DB import
- dashboard, map, forecast explanation template serving

### `map_viewer/`

프론트 템플릿과 정적 UI가 있다.

## 환경변수와 키 관리

절대 Git에 넣지 말 것:

- 실제 API 키
- `ADMIN_KEY`
- DB 비밀번호
- 개인 계정/비밀번호

환경변수 목록은 `.env.example`을 기준으로 한다.

주요 키:

- `DATA_GO_KR_API_KEY`
- `KAMIS_API_KEY`
- `KOSIS_API_KEY`
- `ADMIN_KEY`
- `DATABASE_URL`

현재 로컬 `.env`에는 API 키들이 있으나, 마지막 확인 시 `ADMIN_KEY`는 없었다.

운영 Railway에는 `ADMIN_KEY`가 설정되어 있어야 한다.

## 표준 로컬 실행 순서

### 1. 서비스 카탈로그 확인

```powershell
python scripts\smoke_api_services.py
```

기대:

- total services: 12
- missing required services: 0

### 2. 라이브 API 진단

```powershell
python scripts\run_live_api_diagnostics.py --date 2026-07-01 --item cabbage --max-rows 2 --no-write
```

제공자 `NO_DATA`, `DB_ERROR`, `HTTP_403`은 코드 실패와 분리해서 본다.

### 3. 가격 수집

```powershell
python scripts\collect_live_price_features.py --date 2026-07-01
```

기본:

- 90일
- KAMIS
- AT regional
- AT market settlement

### 4. 생산 통계 수집

```powershell
python scripts\collect_live_production_features.py --date 2026-07-01 --year 2026
```

KOSIS는 최신 연도 데이터가 없으면 과거 연도를 fallback으로 쓸 수 있다.

### 5. 이벤트 수집

```powershell
python scripts\collect_live_event_features.py --date 2026-07-01
```

HTTP/API 오류도 raw/features에 구조화해서 저장하고 계속 진행한다.

### 6. 작물날씨 수집

```powershell
python scripts\collect_live_weather_features.py `
  --date 2026-07-01 `
  --lookback-days 3 `
  --max-requests-per-item 16 `
  --request-timeout-seconds 8
```

운영에서는 반드시 요청 상한을 둔다.

### 7. 전체 파이프라인

전체 수집부터 import 전까지:

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --weather-lookback-days 3 --skip-backend-import
```

이미 수집된 캐시를 재사용:

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --skip-collect --skip-backend-import
```

운영 DB import까지:

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --weather-lookback-days 3
```

## 표준 검증 명령

작업 후 기본 검증:

```powershell
python scripts\run_smoke_suite.py --timeout-seconds 300
```

백엔드 테스트:

```powershell
$venv = Join-Path $env:TEMP 'mkmap-ci-venv-312'
$env:DATABASE_URL='sqlite+aiosqlite:///./test_agri.db'
$env:ADMIN_KEY='test-admin-key'
$env:PYTHONPATH=(Join-Path (Get-Location) 'backend')
& (Join-Path $venv 'Scripts\python.exe') -m pytest backend\tests\test_pipeline.py backend\tests\test_api.py -q
```

비밀값 검색:

```powershell
rg -n "<known-secret-prefix-or-private-identifier>" backend map_viewer scripts docs config mkmap_meta metadata --glob '!*.db' --glob '!*.pyc' --glob '!__pycache__/**'
```

diff check:

```powershell
git diff --check
```

## 운영 서버 확인

공개 상태:

```powershell
Invoke-RestMethod -Uri "https://mk-map.com/health"
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/signals/today"
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/dashboard/cards"
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/items/cabbage/forecast"
```

공개 산출물 자동 검증:

```powershell
python scripts\verify_public_api_outputs.py --expected-date 2026-07-01
```

해석:

- `ok: true`: 공개 API와 예측/위험/가격 산출물이 채워져 있다.
- `missing_data`: 서버는 살아있지만 운영 DB에 pipeline 산출물이 없다.
- `date_mismatch`: 운영 날짜 기준이 기대 날짜와 다르다.
- `--strict`: 실패 상태를 exit code 1로 돌려 CI나 배포 gate에 쓸 수 있다.

Admin 상태:

```powershell
$headers = @{ "X-Admin-Key" = "<ADMIN_KEY>" }
Invoke-RestMethod -Uri "https://mk-map.com/api/v1/admin/status" -Headers $headers
```

원격 pipeline 실행:

```powershell
$headers = @{ "X-Admin-Key" = "<ADMIN_KEY>" }
Invoke-RestMethod `
  -Method Post `
  -Uri "https://mk-map.com/api/v1/admin/meta-pipeline/run?background=false&weather_lookback_days=3&weather_max_requests_per_item=16&weather_request_timeout_seconds=8" `
  -Headers $headers
```

## 품목 추가 방식

새 품목을 추가할 때는 단순히 이름만 추가하지 않는다.

필요 항목:

1. metadata item JSON 추가
2. KAMIS mapping
3. AT regional mapping
4. AT settlement mapping은 정확한 코드가 있을 때만
5. KOSIS production mapping
6. KMA crop weather mapping
7. weather/event sensitivity profile
8. engine plan
9. validation 통과
10. smoke 실행

AT settlement는 추측 금지다. 검색 결과에 유사 품목이 섞이기 쉽다.
## AgroMarket 가격 피처 수집과 학습 테이블 재생성 (2026-07-05)

새로 확보한 AgroMarket API는 가격 예측 우선순위 P0 데이터다. 실제 키는 `.env`의 `AGROMARKET_API_KEY`에만 둔다.

활용 가능성 진단:

```powershell
python scripts\audit_agromarket_data_availability.py `
  --date 2026-07-01 `
  --lookback-days 3 `
  --output data\diagnostics\20260701\agromarket_availability.json
```

가격 피처 수집:

```powershell
python scripts\collect_agromarket_price_features.py `
  --date 2026-07-01 `
  --days-back 60 `
  --rows 100
```

학습 테이블과 모델 재생성:

```powershell
python scripts\build_price_training_table.py --date 2026-07-01
python scripts\train_price_baseline_model.py `
  --input data\model\price_training_table_20260701.csv `
  --output data\model\price_baseline_model_20260701_agromarket.json `
  --report-output data\model\price_baseline_model_20260701_agromarket_evaluation.json `
  --backtest-output data\model\price_baseline_model_20260701_agromarket_backtest.json
python scripts\predict_latest_prices.py `
  --features data\model\price_training_table_20260701.csv `
  --model data\model\price_baseline_model_20260701_agromarket.json `
  --signals data\signals\20260701\region_risk_signals.json `
  --output data\model\latest_price_predictions_20260701_agromarket_risk.json
```

현재 저장 위치:

- 원자료/피처 캐시: `data/features/YYYYMMDD/agromarket_*`
- 진단 결과: `data/diagnostics/YYYYMMDD/agromarket_availability.json`
- 학습 테이블: `data/model/price_training_table_YYYYMMDD.csv`
- 모델/평가/예측: `data/model/*agromarket*`

`data/`는 로컬 캐시/산출물 성격이므로 기본적으로 git commit 대상이 아니다.

## AgroMarket auction volume feature (2026-07-05)

Realtime auction data requires both `SALEDATE` and `WHSALCD`. Current implementation uses Seoul Garak market `110001` as the first stable market-pressure source.

Backfill command:

```powershell
python scripts\collect_agromarket_auction_features.py `
  --date 2026-07-01 `
  --days-back 365 `
  --rows 1000 `
  --max-pages 5
```

If the full command is too slow, run per item:

```powershell
python scripts\collect_agromarket_auction_features.py --date 2026-07-01 --days-back 365 --items onion --rows 1000 --max-pages 4
python scripts\collect_agromarket_auction_features.py --date 2026-07-01 --days-back 365 --items green_onion --rows 1000 --max-pages 3
python scripts\collect_agromarket_auction_features.py --date 2026-07-01 --days-back 365 --items garlic --rows 1000 --max-pages 3
```

Daily pipeline default:

```powershell
python scripts\run_meta_pipeline.py --date 2026-07-01 --auction-days-back 120
```

Current training table uses `agromarket_auction_volume_norm` only. Auction price is intentionally excluded until `STD` package-unit normalization is implemented.

## Horizon-specific price model workflow (2026-07-05)

Purpose:

- Train separate price-change models for each forecast period instead of reusing a next-day target for every UI label.
- Current supported horizons: 1d, 7d, 14d, 30d, 90d, 180d, 365d.

Build training table:

```powershell
python scripts\build_price_training_table.py --date 2026-07-01 --min-history 14
```

The table is stored at:

- `data/model/price_training_table_YYYYMMDD.csv`

Target columns:

- `target_next_change`: legacy next available market point
- `target_1d_change`
- `target_7d_change`
- `target_14d_change`
- `target_30d_change`
- `target_90d_change`
- `target_180d_change`
- `target_365d_change`

Train all horizon models:

```powershell
python scripts\train_price_horizon_models.py `
  --input data\model\price_training_table_20260701.csv `
  --output-dir data\model\horizons `
  --prefix price_horizon_model_20260701_agromarket_365_auction_variant `
  --min-rows 80
```

Output files:

- `data/model/horizons/*_1d.json`
- `data/model/horizons/*_7d.json`
- `data/model/horizons/*_14d.json`
- `data/model/horizons/*_30d.json`
- `data/model/horizons/*_90d.json`
- `data/model/horizons/*_180d.json`
- `data/model/horizons/*_summary.json`

Generate combined latest predictions:

```powershell
python scripts\predict_price_horizons.py `
  --features data\model\price_training_table_20260701.csv `
  --models-dir data\model\horizons `
  --model-prefix price_horizon_model_20260701_agromarket_365_auction_variant `
  --output data\model\latest_price_horizon_predictions_20260701.json
```

Storage rule:

- `data/model/horizons/` contains generated local artifacts.
- These artifacts are reproducible and can stay out of git unless explicitly deciding to version model snapshots.
- Code/config/docs are the source of truth for regeneration.

Current yearly limitation:

- With the current 2025-07-22 to 2026-06-30 local table, `target_365d_change` has 0 usable rows.
- A real yearly model needs at least about two years of price history, preferably three or more.
