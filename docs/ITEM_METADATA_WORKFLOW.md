# Item Metadata Workflow

품목은 `metadata/items/{item_code}.json` 하나를 추가하면 엔진 플랜, 피처 번들, 위험 신호 API까지 같은 흐름으로 확장되도록 설계한다.

## 새 품목 추가

```powershell
python scripts/create_item_metadata.py spinach 시금치 --category 채소류
```

생성된 JSON에서 반드시 검토할 값:

- `growth_calendar`, `harvest_calendar`: 생육/수확 월
- `production_profile.manual_regions`: 주산지 코드, 이름, 가중치
- `market_profile`: 가격 민감도와 가격 반영 지연
- `weather_profile.sensitivity`: 폭염, 한파, 호우, 가뭄 등 기상 민감도
- `event_profile`: 특보, 영향예보, 태풍, 중기예보 반영 비중
- `source_coverage`: KAMIS, KOSIS, data.go.kr 데이터 연결 가능 여부

## 검증

```powershell
python scripts/validate_metadata.py
python scripts/show_engine_plans.py
python scripts/smoke_risk_signal.py
```

검증은 다음을 확인한다:

- 파일명과 `item_code` 일치
- 필수 상위 필드 존재
- 주산지 가중치가 비어 있지 않고 합계가 과도하지 않음
- `risk_signal` 엔진 포함
- 위험 기상요소와 민감도 정의 일치
- 이벤트별 가중치 정의 누락 여부
- 승인받은 data.go.kr 서비스 코드만 사용

## 운영 반영 순서

1. 품목 JSON 초안 생성
2. 주산지/생육/수확/이벤트 민감도 보정
3. `validate_metadata.py` 통과
4. API 서비스 상세 URL과 파라미터를 환경변수에 연결
5. `export_signals.py` 또는 FastAPI 라우터에서 신호 확인

