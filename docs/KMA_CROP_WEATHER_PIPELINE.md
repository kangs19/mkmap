# KMA Crop Weather Pipeline

This pipeline maps MK-MAP item metadata to the official KMA crop main-area weather API codes and stores normalized weather features for downstream risk and price engines.

## Source

- data.go.kr API: `기상청_작물별 농업주산지 상세날씨 조회서비스`
- Official guide page: `https://www.data.go.kr/data/15059518/openapi.do`
- Reference document file id: `FILE_000000003577750`
- Code table inside the guide: `작물별_농업주산지_상세날씨_조회서비스__지역코드_20260105.xlsx`

The guide ZIP is downloaded locally when needed, but it is ignored by Git. The committed artifact is the extracted CSV:

```text
config/external_mappings/kma_crop_weather_mapping.csv
```

## Mapping Shape

Some items have multiple crop-specific IDs by season, variety, or cultivation type. For example, cabbage has spring, highland, autumn, and winter variants. Metadata therefore stores mappings per row:

- `area_id`
- `area_name`
- `pa_crop_spe_id`
- `pa_crop_spe_name`
- optional address and coordinates

The connector calls the KMA API once per unique `area_id + pa_crop_spe_id` pair.

## Commands

```powershell
python scripts\extract_kma_crop_weather_mapping.py --download
python scripts\import_kma_crop_weather_mapping.py --apply
python scripts\validate_external_mappings.py
python scripts\test_live_kma_crop_weather.py --item garlic --date 2025-06-29
python scripts\collect_live_weather_features.py --date 2025-06-29
python scripts\build_model_dataset.py --date 2025-06-29
python scripts\export_live_signals.py --date 2025-06-29
```

## Current Run

- `2025-06-29` collection succeeded for all 5 items.
- Extracted mapping rows: cabbage 63, radish 40, onion 14, green onion 49, garlic 29.
- Collected weather features: cabbage 62, radish 40, onion 13, green onion 49, garlic 28.
- `2026-06-29` returned `NO_DATA` from the KMA service during testing, so current-date collection may need retry or a provider-side data availability delay.

## Notes

- `NO_DATA` and other public API error headers are not converted into features.
- Generated raw and feature files under `data/` are ignored by Git.
- `CachedWeatherConnector` reads `data/features/{YYYYMMDD}/kma_crop_weather_{item}.json` and feeds model dataset and signal export scripts.
