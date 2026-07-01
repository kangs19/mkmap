# MK-MAP Next Roadmap

마지막 업데이트: 2026-07-01 KST

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
   - `DATA_GO_KR_API_KEY`
   - `KAMIS_API_KEY`
   - `KOSIS_API_KEY`

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

현재 RDA agri weather는 endpoint diagnostic이 붙어 있으나, 관측소 코드/지역 매핑이 약하다.

해야 할 일:

- RDA 관측소 코드 목록 확보
- 품목 주산지와 RDA 관측소 매핑
- `RDA_AGRI_WEATHER_OBSR_SPOT_CD` 고정값이 아니라 품목/지역별 mapping으로 확장
- RDA weather feature를 CachedWeatherConnector 기본 source에 포함할지 결정

성공 기준:

- RDA feature가 품목별로 1개 이상 수집된다.
- risk signal에서 KMA crop weather와 충돌 없이 보조 weather source로 쓰인다.

## P1: AT 정산정보 품목 매핑 확장

현재 안전하게 일부 품목만 AT settlement mapping을 활성화했다.

주의:

- 배추/무는 유사 품목명이 많아 broad query로 잘못 매핑하면 안 된다.
- 예: 얼갈이, 양배추, 열무, 자두 후무사 같은 오염 가능성이 있었다.

해야 할 일:

- 공식 코드표 또는 실제 endpoint filtered 결과로 정확한 대분류/중분류/소분류 코드 확인
- 배추/무 정산 mapping 추가
- `scripts/test_live_at_market_settlement.py`로 live 확인

성공 기준:

- 배추/무 정산정보가 정확한 품목명으로만 나온다.
- risk signal market pressure에 settlement source가 포함된다.

## P2: 모델 품질 개선

현재 모델은 baseline linear model이다.

현재 확인된 결과:

- 2026-07-01 cached run
- train rows: 120
- test rows: 30
- features: 20
- direction threshold: 0.0295
- accepted item models: 1
- MAE: 0.015109
- RMSE: 0.019224
- sign accuracy: 0.4333
- 3-class direction accuracy: 0.9667

해야 할 일:

- 더 긴 가격 history 확보
- AT/KAMIS 단위 차이 정규화
- wholesale/retail/settlement 각각 별도 feature로 분리
- 품목별 item model acceptance gate 개선
- rolling backtest window 확대
- 외부 위험 신호의 price adjustment scale 검증

## P2: 프론트 UI 실제 데이터 대응

현재 공개 dashboard cards는 데이터가 없으면 안내 문구를 반환한다.

해야 할 일:

- 데이터 없음 상태 UI 개선
- last pipeline status 표시
- freshness 표시
- forecast explanation 페이지에서 KST 기준 date 표시
- 데이터가 null일 때 카드 레이아웃 깨짐 확인

## P2: API 진단 결과 운영 UI 연결

이미 admin status는 latest diagnostic을 노출한다.

더 할 일:

- live diagnostics를 scheduler 후 자동 실행할지 결정
- provider no_data/api_error를 색상/문구로 구분
- KMA satellite HTTP_403 같은 승인 문제는 별도 “권한 확인 필요”로 표시

## P3: 자동화와 운영 알림

해야 할 일:

- daily pipeline 성공/실패 Discord 알림 강화
- 실패 step 표시
- forecast count, signal count, public verify 결과 포함
- Railway restart 후 auto-recover 결과 알림

## 계속 업데이트할 것

작업을 끝낼 때마다 이 파일의 각 항목 상태를 수정한다.

형식:

- 완료됨
- 진행 중
- 보류
- 실패 원인
- 다음 액션
