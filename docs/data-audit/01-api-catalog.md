# 01. API 목록 & Data Catalog

각 데이터셋 카드: 데이터명·제공기관·수집방법·갱신주기·주요컬럼·기본키·사용목적·품질등급(A/B/C)·담당Feature·최종검증일(2026-07-04).
품질등급: A=학습 즉시가능, B=보강 후 가능, C=연구/추가확보 필요.

---
### KAMIS 농산물 가격
- 제공기관: 한국농수산식품유통공사(aT) / KAMIS
- 수집: API (`kamis.or.kr/service/price/xml.do`, action=periodProductList)
- 갱신: **일별** (전일 확정치 익일 오전)
- 이력: **2013~** (10년+, 프로빙 확인)
- 주요컬럼: productno, dpr1(가격), product_cls_code(02도매/01소매), dpr5(평년), dpr6(전년)
- 기본키: (productno, date, cls, market)
- 단위: 배추10kg·무20kg·양파20kg·대파1kg·마늘20kg·건고추30kg·참깨30kg (품목별 상이)
- 목적: 예측 타깃·차트·lag/MA 피처
- 품질: **A** / 담당Feature: price_* / 이용제한: 인증키, 상업적 재배포 제한

### MAFRA 실시간 경매정보 (654)
- 제공기관: 농림축산식품부 / aT 도매시장통합
- 수집: API (`api.agromarket.kr/api/katRealTime/v2/trades`, cond[trd_clcln_ymd::EQ])
- 갱신: **일별**(경매 새벽~오전, 정산 당일 완결)
- 주요컬럼: whsl_mrkt_cd/nm, corp_gds_item_nm, gds_l/m/sclsf_nm, scsbd_prc(낙찰가), qty(거래량), plor_nm(산지), unit_qty/nm
- 기본키: auctn_seq
- 목적: 지역 도매가(경락), 출하비중(산지×물량), 물량 피처
- 품질: **A** / 담당: regional_price, shipment_share, volume / IP 등록 필요(152.55.176.234)

### MAFRA 도매/소매/친환경 가격 (217/163/160)
- 수집: `api.agromarket.kr/api/perDay/v1/price`(일별), `perRegion/v1/price`(지역별)
- 필수: serviceKey, cond[exmn_ymd::GTE/LTE], cond[item_cd::EQ]+cond[ctgry_cd::EQ] 또는 cond[sgg_cd::EQ]
- 코드: `api.agromarket.kr/api/katCode/v1/goods` (gds_l/m/sclsf, 15,436건)
- 목적: **실측 소매가**(현재 도매×1.35 추정 대체), 유통 마진
- 품질: **B**(코드 매핑 필요) / 담당: retail_price

### MAFRA 정산 물량/금액 (658)
- 수집: 211.237 / agromarket 채널, 날짜 필터 필요
- 내용: 도매시장별 품목별 총물량·총금액 → **공급량 선행지표**
- 품질: **B** / 담당: supply_volume

### MAFRA 저수율·강수 (669)
- 수집: `211.237.50.150:7080/openapi/{key}/json/Grid_20250220000000000669_1/{s}/{e}` (무필터)
- 갱신: **월별**(TOT_YM) + STR_DT 일자, 이력 **2019.01~2026.07(91개월)**, 64,784건
- 컬럼: TOT_YM, AREA_SPR_CD(저수지코드), RNFL_MSRVL(강수mm), STWTR_RTO_MSRVL(저수율%)
- 목적: 가뭄 리스크, 공급 위험
- 품질: **B** / 담당: drought_index / ⚠️ AREA_SPR_CD 시군구 매핑 불가(코드표 필요)

### MAFRA 기상특보·재해보험 (671)
- 수집: 211.237, 무필터. 이력 **2020.01~2027.01(85개월)**, 11,911건
- 컬럼: BJDNGCD(법정동), *_SPCRPT_CNT(태풍/폭염/한파/호우/대설/강풍/황사 특보건수), JOIN_PRCL_CNT/JOIN_SFC(보험가입 필지/면적)
- 목적: 재해 리스크, 지역 취약도
- 품질: **B**(최신성 낮음) / 담당: disaster_risk

### KMA 기상
- 제공기관: 기상청
- 수집: API 단기예보(getVilageFcst), 농업주산지(kma_agri). KST 기준.
- 갱신: 일별(예보). **과거 관측(ASOS/AWS)은 별도 API 필요**
- 컬럼: 기온(평균/최고/최저), 강수, 습도, (풍속/일조 확장)
- 목적: 기상 피처, 생육 스트레스
- 품질: **A(예보)/B(과거관측 미확보)** / 담당: weather_*

### KOSIS 생산량·재배면적
- 제공기관: 통계청 KOSIS
- 수집: API. **제공키(cc987625…) 무효 확인 → 재발급 필요**
- 갱신: **연별**, 품목별 전국(시군구 분해 제한)
- 목적: 공급 규모, 시즌 상수 피처
- 품질: **C(키 재발급 전까지)** / 담당: production_*

### FarmMap 병해충·토양·농업기상
- 제공기관: 농림수산식품교육문화정보원 / data.go.kr B552895
- 엔드포인트: `apis.data.go.kr/B552895/rest/farmmap/*` (좌표기반)
- 상태: **키 401(미인증)** → data.go.kr 서비스 등록/키형식 검증 필요
- 잠재: 병해충 발생, 토양검정(pH/수분), 필지 작물분포
- 품질: **C** / 담당: pest_*, soil_*

### (미확보/추가) 관세청 수입, 한국은행 환율, 통계청 소비
- 수입량·수입단가(관세청), 환율(ECOS), 소비/가계(통계청) — 향후 연동. 품질 **C**.
