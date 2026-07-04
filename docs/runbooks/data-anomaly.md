# Runbook: 데이터 이상치 (가격 급등·품종 혼입 등)

## 감지 (Detect)
- 특정일 급등(예: 마늘 10배), 지역가 튐

## 조치 (Steps)
1. 원본 소스 vs 저장값 비교
2. 가드: KAMIS _reject_price_outliers(중앙값 4배), 지역가 시장내/시장간 트림
3. 품종 혼입은 _is_std_variety 필터
4. 기존 오염행은 날짜별 삭제 후 재수집

## 사후 (Postmortem)
원인·조치·재발방지를 docs/runbooks 또는 ADR에 기록.
