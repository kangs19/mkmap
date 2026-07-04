# ADR-009. 가격모델 Champion/Challenger 자동 검증

- Status: Accepted
- Date: 2026-07-04

## Context
모델 변경(피처 추가 등)이 실제로 정확도를 올리는지 검증 없이 프로덕션에 넣으면 위험하다.

## Decision
파이프라인이 v1(baseline)·v2(물량·날씨·작물별 피처) 둘 다 학습→홀드아웃 direction_accuracy 비교→v2가 +0.5%p 이상+누수가드 통과 시에만 채택. 실패 시 v1 유지.

## Consequences
장점: 무위험 자동 개선. 결과는 /api/v1/model/champion-challenger. (Bible Vol.5)
