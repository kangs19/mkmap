# Runbook: 예측 생성 실패 / 이상값

## 감지 (Detect)
- forecasts base_date 미갱신
- 방향-확률 모순, 단위 이상값

## 조치 (Steps)
1. import_meta_outputs 로그 확인
2. Champion/Challenger 결과(/api/v1/model/champion-challenger)
3. 방향은 확률에서 유도되는지(일관성)
4. 가격 이상치 가드(sync _reject_price_outliers) 동작 확인

## 사후 (Postmortem)
원인·조치·재발방지를 docs/runbooks 또는 ADR에 기록.
