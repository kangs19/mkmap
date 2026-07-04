# ADR-005. AI 예측과 사용자/커뮤니티 데이터 분리

- Status: Accepted
- Date: 2026-07-04

## Context
신뢰성을 위해 공공데이터 기반 AI 예측과 사용자 제보를 섞지 않아야 한다(PRD 핵심 원칙).

## Decision
prediction_* 와 community_*/field_report 를 물리적으로 분리 저장. 현장 제보는 초기 AI 학습에 미사용, '현장 신호'로만 표시.

## Consequences
장점: 신뢰·설명가능성. 향후 검증된 현장 데이터만 보조 Feature 연구 대상.
