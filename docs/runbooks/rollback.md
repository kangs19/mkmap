# Runbook: 롤백

## 감지 (Detect)
- 배포 후 오류/회귀

## 조치 (Steps)
1. git log로 직전 정상 커밋 확인
2. git revert <bad> 후 push → Railway 자동 재배포
3. /health·핵심 엔드포인트 스모크
4. 원인 커밋 기록

## 사후 (Postmortem)
원인·조치·재발방지를 docs/runbooks 또는 ADR에 기록.
