# ADR-007. Feature Store — 현재 파일(CSV), DB 이관 목표

- Status: Proposed
- Date: 2026-07-04

## Context
모델은 단일 Feature 소스만 사용해야 재현성이 보장된다. 현재는 build_price_training_table 산출 CSV.

## Decision
단기: CSV 기반 Feature 파이프라인 유지(mkmap_meta). 장기: feature_daily 테이블화로 중앙 Feature Store 구축.

## Consequences
장점: 재현성. 이관 시 predict가 같은 CSV/테이블을 읽으므로 build만 바꾸면 train/predict 자동 반영.
