# Session 80 - 장기 예측 정책 UI 연결

Date: 2026-07-06

## 왜 했나

이전 작업에서 백엔드 공개 API는 180일/365일 예측을 `hidden_horizons`로 분리하도록 바뀌었다. 하지만 프론트는 `forecast.horizons`만 저장하고 정책 필드를 버리고 있어서, 사용자가 왜 6개월/1년 예측이 안 보이는지 화면에서 알기 어려웠다.

## 변경 내용

- `index.html`에 `LIVE_HORIZON_POLICIES` 상태를 추가했다.
- `fetchItemForecast()`가 다음 값을 저장하게 했다.
  - `forecast.horizon_policy`
  - `forecast.hidden_horizons`
  - 품목별 `LIVE_ITEMS[item_code].hidden_horizons`
- `hiddenHorizonDays()`와 `horizonPolicyText()`를 추가했다.
- 상단 `예측 판단` 패널에서 장기 예측이 숨겨진 경우 다음 판단을 우선 표시한다.
  - 6개월/1년 숫자 예측보다 1주~3개월 구간의 검증된 가격 방향을 먼저 본다.
  - 장기 예측은 백테스트와 방향 정확도가 충분히 쌓이면 다시 연다.
- 오른쪽 상세 `가격 예측` 탭에 `장기 예측 판단` 안내 영역을 추가했다.
- 현재 공개 기간은 계속 1주, 2주, 3주, 4주, 2개월, 3개월까지만 유지한다.

## 검증

- `cd backend; $env:PYTHONPATH=(Get-Location).Path; pytest tests\test_api.py -q`
  - 결과: 36 passed
- `python scripts\run_smoke_suite.py --timeout-seconds 300`
  - 결과: passed
- 로컬 서버 `http://127.0.0.1:8021/?v=horizon-policy-local-3`
  - 브라우저 로드 정상
  - `window.__codexErrors`: `[]`

## 확인된 상태

- 현재 로컬/운영 배추 forecast는 horizon 파일 응답이 아니라 DB fallback 형태로 내려와 `hidden_horizons`가 실제 화면에는 아직 나타나지 않는다.
- horizon 파일 기반 응답이 활성화되면 같은 UI가 자동으로 장기 예측 보류 문구를 표시한다.

## 다음 작업

1. 운영 `ACTIVE_PRICE_PREDICTIONS_PATH`가 horizon 파일을 바라보는지 확인한다.
2. horizon 파일 응답이 활성화된 상태에서 실제 `hidden_horizons` UI 표시를 브라우저로 재검증한다.
3. 장기 예측은 숫자 대신 “장기 상승/하락 압력”으로 보여줄지 UX를 별도 설계한다.
4. 현재 DB fallback `/forecast` 응답도 가능하면 `horizon_policy`를 내려주도록 통일할지 검토한다.
