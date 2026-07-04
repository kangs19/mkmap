# Runbook: 외부 공공API 장애 (KAMIS/KMA/KOSIS/MAFRA)

## 감지 (Detect)
- 스케줄러 로그의 sync 실패, saved=0
- 해당 엔드포인트 데이터 미갱신(예: 날씨 base_date 정체)

## 조치 (Steps)
1. /health, 해당 map/* 엔드포인트로 최신일 확인
2. 키 유효성·쿼터 확인(env)
3. 시간대(KST) 이슈 확인 — sync는 kst_today()/kst_now() 사용
4. days_back 겹침으로 자동 보충되는지 확인
5. 필요시 수동 재수집 트리거

## 사후 (Postmortem)
원인·조치·재발방지를 docs/runbooks 또는 ADR에 기록.
