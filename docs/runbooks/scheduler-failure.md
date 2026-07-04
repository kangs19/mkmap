# Runbook: 스케줄러/파이프라인 실패

## 감지 (Detect)
- /health scheduler=false
- 당일 signals/forecasts 미생성

## 조치 (Steps)
1. 재배포 시 auto_recover가 당일 산출 없으면 재실행
2. Discord 알림(notify_pipeline_error) 확인
3. run_meta_pipeline 로그 tail 확인
4. 개별 스텝(build/train/predict/import) soft_fail 여부

## 사후 (Postmortem)
원인·조치·재발방지를 docs/runbooks 또는 ADR에 기록.
