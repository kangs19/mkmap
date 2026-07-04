# API 서비스 모듈 맵 (Phase 2 이관 대상)

PRD/Bible의 서비스 모듈 경계. 현재 라우터를 목표 모듈로 점진 이관(URL 유지).

## 목표 모듈 (Bible Vol.1 §1.4)
| 모듈 | 책임 | 현재 위치 | 이관 |
|------|------|----------|------|
| Auth/User | 회원·인증·권한 | auth_user.py, rbac.py | 유지 |
| Region | 지역 마스터 | (items 내부) | 분리 검토 |
| Crop(Item) | 품목 마스터·카탈로그 | items.py | 유지 |
| Market | 가격·경매·거래량·지역가 | maps.py(혼재) | **분리 대상** |
| Weather | 기상·저수율·특보 | maps.py, drought | **분리 대상** |
| Prediction | 예측·리스크·설명 | forecasts.py, signals.py | 유지 |
| Community | 커뮤니티·현장제보 | community.py | 유지 |
| Admin | 운영·수집 트리거 | admin.py | 유지 |

## 우선 이관 (다음 반복)
maps.py가 지도·가격·날씨·저수율·출하·choropleth를 혼재 → 도메인 분리:
- market_router: /api/v1/map/prices, /regional-prices, /shipment-share
- weather_router: /api/v1/map/weather, /api/v1/drought
- (URL 경로는 그대로 두고 파일만 분리 → 프론트 무영향)

## 표준
- 응답: app/response.py envelope (신규부터)
- 권한: app/rbac.py (신규부터)
- 첫 채택: GET /api/v1/items/catalog
