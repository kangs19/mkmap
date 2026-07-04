# 02. 데이터 사전 (Data Dictionary) — 현행 DB 테이블

운영 PostgreSQL의 실제 테이블. 향후 계층 네이밍(core_/feature_/prediction_)으로 정렬 예정(Phase 3).

| 테이블 | 목적 | 주요 컬럼 | 키 | 소스 |
|--------|------|----------|-----|------|
| daily_prices | 일별 가격 | item_code, date, wholesale_price, retail_price, avg_year_price, prev_year_price, market, grade | (item_code,date,source) | KAMIS |
| daily_market | 거래량/반입 | item_code, date, market, origin_region, volume_kg, trade_volume, trade_amount | (item,date,market,source) | KAMIS/경락 |
| daily_weather | 기상 | region_code, date, avg/max/min_temp, precipitation, humidity, *_alert, normal_avg_temp | (region_code,date,source) | KMA |
| regional_market_price | 지역 도매가(경락) | item_code, date, market_code, market_name, sido, wholesale_price, retail_price | uq(item,date,market_code) | 경락(654) |
| shipment_share | 출하비중 | item_code, sido, base_date, share_pct, volume | uq(item,sido,base_date) | 경락 산지 |
| drought_index | 저수율 지표 | base_ym, date, reservoir_rate, rainfall_avg, region_count | uq(base_ym) | MAFRA 669 |
| crop_production | 생산/재배 | item_code, year, area_ha, production_ton, source | (item,year) | KOSIS |
| region_signals | 지역 리스크 | item_code, region_code, date, risk_score, risk_level, price_effect, summary | (item,region,date) | 파생 |
| forecasts | 예측 | item_code, base_date, horizon_days, direction/direction_14d, up_probability(_14d), surge/bottom_prob, top_factors, confidence | uq(item,base_date,horizon) | 모델 |
| item_meta | 품목 메타 | item_code, ... (단수/시즌 등) | item_code | 내부 |
| items / item_region | 마스터 | item_code, item_name, category, region | - | 내부 |
| users / community_comments / field_reports / phone_verifications | 커뮤니티·회원 | (ADR-005: 예측과 분리) | - | 사용자 |

## 코드/단위 참조
- 품목 단위·코드: `backend/app/collectors/kamis.py` ITEM_CODE_MAP (단일 출처, GET /api/v1/items/catalog로 노출)
- 지역: KR-XX(시도) + 시군구명 (표준 법정동 매핑은 미구축 → [03-code-mapping.md])

## 시간축
- 일별: daily_prices, daily_market, daily_weather, regional_market_price, forecasts
- 월별(전개 필요): drought_index(669), 특보(671)
- 연별(시즌화): crop_production(KOSIS)
