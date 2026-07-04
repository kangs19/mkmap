# ADR-008. 설명가능한 AI (XAI)

- Status: Accepted
- Date: 2026-07-04

## Context
AI는 가격을 맞추는 게 아니라 의사결정을 돕는 엔진. 모든 예측은 설명·측정·추적 가능해야 한다.

## Decision
예측마다 상위 영향요인(top_factors)+자연어 헤드라인 제공. 방향은 상승확률에서 일관 유도. 예측 이력 영구 보존.

## Consequences
장점: 신뢰. 향후 SHAP 기반 기여도로 고도화.
