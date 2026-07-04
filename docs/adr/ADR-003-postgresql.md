# ADR-003. 주 데이터베이스 PostgreSQL (Railway)

- Status: Accepted
- Date: 2026-07-04

## Context
시계열 가격·예측 이력·관계형 커뮤니티 데이터를 안정적으로 저장해야 한다. 예측·시장 이력은 immutable.

## Decision
Railway PostgreSQL 애드온을 주 DB로 사용. SQLAlchemy async(asyncpg). 로컬은 sqlite 폴백.

## Consequences
장점: 관리형, 관계·인덱스·upsert. init_db에서 스키마 마이그레이션(ALTER IF NOT EXISTS) 관리.
