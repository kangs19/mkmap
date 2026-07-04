# ADR-001. Region × Item을 모든 데이터의 기본 키로 사용

- Status: Accepted
- Date: 2026-07-04

## Context
가격·기상·경매·생산·커뮤니티 등 모든 도메인 데이터가 '어느 지역의 어느 품목'인지로 귀결된다. 서비스·지도·AI·커뮤니티가 동일한 축을 공유해야 일관성이 생긴다.

## Decision
모든 테이블과 API는 region_code × item_code(crop_code)를 1차 비즈니스 키로 삼는다. 신규 산업(축산/수산)도 동일 구조(Region × Item)로 확장한다.

## Consequences
장점: 도메인 일관성, 확장성. 주의: 신규 데이터 추가 시 반드시 region×item에 매핑해야 함. (PRD Ch.2/3, Bible Vol.2)
