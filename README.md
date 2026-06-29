# mkmap

MK-MAP은 품목별 농산물 가격 리스크를 주산지, 기상, 재해 이벤트, 가격 데이터를 묶어 지도형 신호로 만드는 프로젝트입니다.

## Metadata Engine

품목 확장은 `metadata/items/{item_code}.json` 파일을 추가하는 방식으로 진행합니다. 메타데이터가 등록되면 엔진 플랜, 피처 번들, 위험 신호 생성 흐름이 같은 구조로 동작합니다.

```powershell
python scripts/validate_metadata.py
python scripts/show_engine_plans.py
python scripts/build_feature_bundles.py
python scripts/smoke_risk_signal.py
```

새 품목 초안은 아래처럼 만들 수 있습니다.

```powershell
python scripts/create_item_metadata.py spinach 시금치 --category 채소류
```

자세한 품목 추가 절차는 `docs/ITEM_METADATA_WORKFLOW.md`를 참고하세요. 외부 API 코드 매핑 상태는 `docs/API_SOURCE_MAPPING.md`에 정리합니다.

## Environment

실제 API 키는 저장소에 넣지 않습니다. 로컬에서 `.env.example`을 참고해 `.env`를 만들면 스크립트와 API 서비스가 자동으로 읽습니다.

```powershell
Copy-Item .env.example .env
```

`.env`에는 `DATA_GO_KR_API_KEY`, `KAMIS_API_KEY`, `KOSIS_API_KEY` 같은 실제 키를 넣습니다. `.env`는 `.gitignore`에 포함되어 있어 Git에 올라가지 않습니다.

가격 예측 1차 파이프라인은 [docs/PRICE_MODEL_PIPELINE.md](docs/PRICE_MODEL_PIPELINE.md)에 정리되어 있습니다.
KOSIS 생산통계 수집 파이프라인은 [docs/KOSIS_PRODUCTION_PIPELINE.md](docs/KOSIS_PRODUCTION_PIPELINE.md)에 정리되어 있습니다.

## Checks

```powershell
python scripts/show_api_services.py
python scripts/validate_api_catalog.py
python scripts/smoke_env_loading.py
python scripts/check_env_status.py
python scripts/preview_api_requests.py
python scripts/smoke_api_services.py
python scripts/show_external_mapping_status.py
python scripts/validate_external_mappings.py
python scripts/import_kma_crop_weather_mapping.py
python scripts/smoke_kma_mapping_import.py
python scripts/test_live_kma_crop_weather.py --item cabbage --date 2026-06-29
python scripts/test_live_weather_alert.py --date 2026-06-29
python scripts/test_live_typhoon.py --date 2026-06-29
python scripts/test_live_midterm_forecast.py --date 2026-06-29
python scripts/collect_live_event_features.py --date 2026-06-29
python scripts/export_live_signals.py --date 2026-06-29
python scripts/build_model_dataset.py --date 2026-06-29
```
