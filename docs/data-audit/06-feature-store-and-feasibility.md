# 06. 데이터 연결 구조도 · Feature Store 설계 초안 · 모델 가능성 평가

## 6.1 데이터 연결 구조도 (조인)
```
                    [ region_map ]      [ item_map ]
                    (source→bjd_cd)     (source→item/variety)
                          │                    │
   ┌──────────┬──────────┼──────────┬─────────┼──────────┐
   │          │          │          │         │          │
 KAMIS     경락(654)   KMA기상    저수율669  KOSIS생산  특보671
 가격       낙찰·물량   (예보)     (월·전국)  (연)       (월·법정동)
   │          │          │          │         │          │
   └──────────┴──────────┴────┬─────┴─────────┴──────────┘
                              ▼
                   조인키: item_code × region × date
                              ▼
                    [ feature_daily ]  ← 단일 Feature Store
                              ▼
                     학습(build→train→predict)
```
- **조인키 = 품목 × 지역 × 날짜**. 월/연 데이터는 날짜로 forward-fill(월값을 그 달 일자에 전개), 생산은 연 상수/시즌.
- 지역 축은 두 레벨: 전국(national) / 시도(sido) / (향후 시군구). 저수율은 현재 national만.

## 6.2 Feature Store 설계 초안
### 테이블 `feature_daily`
- PK: (item_code, region_level, region_code, date)
- 컬럼군:
  - price_*: lag/ma/change/volatility, 전년·평년, 도소매갭
  - volume_*: 반입량·물량변화·출하비중
  - weather_*: 기온(평/최고/최저)·강수·습도·GDD·특보일수
  - reservoir_*: 저수율·누적강수(전국)
  - disaster_*: 특보건수·보험취약도
  - production_*: 재배면적·생산량·단수(연→전개)
  - season_*: month/weekday sin·cos, 명절·김장 플래그
  - external_*: (향후) 수입·환율·소비·병해충·토양
  - target: next_change (예측 대상)
- 원칙(ADR-007): 모델은 feature_daily만 소비. 재현성 위해 build 시점 스냅샷.
- 현재: CSV(build_price_training_table_v2) → 향후 이 테이블로 이관.

### 파이프라인
`수집(raw) → 정규화(core, 코드매핑) → feature_daily → 학습/추론 → 예측이력`
(PRD Ch.2 Raw→Normalized→Feature→Prediction 준수)

## 6.3 모델 개발 가능성 평가
| 조건 | 평가 |
|------|------|
| 가격 히스토리 | ✅ 10년+ 일별(KAMIS) — baseline 충분 |
| 외생 피처 | 🔶 기상(예보)·물량·저수율 확보, 과거관측·생산·병해충은 보강필요 |
| 라벨(타깃) | ✅ next_change 산출 가능 |
| 조인 가능성 | 🔶 코드 매핑 마스터 구축 시 가능(현재 시도까지) |
| 검증 체계 | ✅ Champion/Challenger·holdout(ADR-009) 이미 구축 |

**결론: baseline 가격예측 모델 개발 가능**(가격+계절+기상예보+물량). 정확도 고도화는
① 지역·품목 코드 매핑 ② 품종 분리 ③ 과거 기상 백필 ④ 생산/병해충/외생 확보 순.

## 6.4 다음 단계 (Phase 2 제안 — 모델 아님, 데이터 기반공사)
1. region_map / item_map 마스터 테이블 구축 (R1·R2)
2. KOSIS·FarmMap 키 정상화 (R3·R4)
3. KMA ASOS/AWS 과거 관측 백필 (R5)
4. feature_daily 테이블화 + build 파이프라인 이관 (ADR-007)
5. Data Catalog 지속 갱신([01-api-catalog.md]) — 신규 작물/국가 확장 시 동일 기준 검증
