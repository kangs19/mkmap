# Session 79 - 기간별 예측 공개 게이트

Date: 2026-07-06

## 왜 했나

사용자가 지적한 것처럼 6개월/1년 예측은 현재 화면에서 신뢰도가 낮아 보이며, 가격 동향 분석도 충분한 검증 없이 장기 숫자를 보여주면 서비스 신뢰를 떨어뜨린다. UI에서만 숨기면 API나 다른 화면에서 다시 섞일 수 있으므로 백엔드 공개 응답 단계에서 정책을 고정했다.

## 변경 내용

- 공개 예측 최대 기간을 `90일`로 제한했다.
- `backend/app/services/horizon_forecasts.py`에 `PUBLIC_MAX_HORIZON_DAYS = 90`을 추가했다.
- `/forecast`와 `/forecast/explanation` 응답을 만들 때 다음 horizon은 공개 active 목록에서 제외한다.
  - 90일을 초과하는 기간: 180일, 365일 등
  - 모델 산출물에서 `held_out=true`로 표시된 기간
- 제외된 기간은 `forecast.hidden_horizons`와 `forecast.horizon_policy`에 남긴다.
- 대표 예측 후보 순서를 `30일 -> 90일 -> 14일 -> 7일 -> 1일`로 바꿨다.
- 180일/365일은 충분한 백테스트와 방향 정확도 검증을 통과하기 전까지 대표 예측으로 쓰지 않는다.

## 검증

- `cd backend; $env:PYTHONPATH=(Get-Location).Path; pytest tests\test_horizon_forecasts.py -q`
  - 결과: 2 passed
- `cd backend; $env:PYTHONPATH=(Get-Location).Path; pytest tests\test_api.py -q`
  - 결과: 36 passed

## 새 테스트

- `backend/tests/test_horizon_forecasts.py`
  - 14/30/90일은 공개 active로 남는지 확인한다.
  - 180/365일은 `hidden_horizons`로 빠지는지 확인한다.
  - `held_out=true`인 7일 예측도 active에서 제외되는지 확인한다.
  - 설명 응답의 `reasons_by_horizon`도 공개 horizon만 포함하는지 확인한다.

## 다음 작업

1. 장기 예측 품질 리포트를 실제 운영 파이프라인 산출물과 연결한다.
2. 180일/365일을 다시 열 수 있는 조건을 코드/문서에 명확히 둔다.
   - backtest prediction count >= 100
   - backtest direction accuracy >= 0.70
   - test direction accuracy >= 0.60
   - horizon 간 성능 편차가 과도하지 않을 것
   - temporal robustness hold가 없을 것
3. UI 가격 예측 탭에서 `hidden_horizons`가 있으면 “장기 예측은 검증 중” 정도로 작게 안내할 수 있다.
4. 긴 기간을 공개하기 전에 실제 사용자에게 숫자 예측이 아니라 “장기 상승/하락 압력” 형태로 먼저 보여줄지 검토한다.

## 작업 원칙

- 검증되지 않은 기간의 숫자 예측은 공개하지 않는다.
- 사용자는 기능 설명보다 “그래서 지금 어떻게 봐야 하는지”를 원한다.
- 모델이 흔들리는 구간은 숨기거나 보류 상태로 표시하고, 임의 숫자로 채우지 않는다.
- 백엔드 API 정책을 먼저 고정한 뒤 UI를 맞춘다.
