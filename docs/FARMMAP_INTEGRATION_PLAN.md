# FarmMap Integration Plan

Date: 2026-07-05 KST

Goal: connect FarmMap spatial crop data to MK Map without showing unsourced or fake crop-region values.

## What FarmMap Can Add

- parcel or field-level agricultural boundaries.
- crop/land-use spatial context when the source file includes crop attributes.
- cultivation area by crop and region.
- spatial joins between crop area, weather risk, soil/pest data, and market influence.

## Integration Rule

Raw FarmMap geometry must not be sent directly to the browser unless it is simplified or tiled. The production path is:

1. download official FarmMap SHP/CSV/GeoJSON source files.
2. audit fields and crop names.
3. normalize crop names with `config/farmmap_crop_aliases.json`.
4. aggregate by `item_code + sido + sigungu`.
5. store summaries in `farmmap_crop_regions`.
6. expose only summarized/simplified map payloads.
7. feed area/risk shares into the price feature engine.

## New Storage

- `farmmap_source_files`
  - one row per audited FarmMap source file.
  - stores detected fields, detected crop names, format, province, and import status.
- `farmmap_crop_regions`
  - one row per normalized crop-region summary.
  - stores item code, source crop name, sido, sigungu, area, farm count, source file, year, and confidence.

## Crop Alias Scope

Current MVP crops:

- `cabbage`: 배추 and known seasonal/subtype names.
- `radish`: 무 and known seasonal/subtype names.
- `onion`: 양파 and maturity/storage variants.
- `green_onion`: 대파 plus related 파 names, with lower confidence for 쪽파/실파.
- `garlic`: 마늘 and storage/type variants.

Alias file:

- `config/farmmap_crop_aliases.json`

## First Validation Checklist

- Does the source file include a crop name column?
- Does the source file include area in square meters, hectares, or pyeong?
- Does it include region fields such as 시도/시군구, 법정동, PNU, or FarmMap ID?
- Does geometry exist and is it valid enough for simplification?
- Are the crop names compatible with our item aliases?
- Does the source license allow public map rendering?

## Next Implementation Steps

1. Run `scripts/audit_farmmap_spatial_file.py --input <downloaded-file>`.
2. Review detected fields/crops.
3. If crop and area fields exist, run a region-summary importer.
4. Import the summary:
   - local: `python scripts/import_farmmap_crop_region_summary.py --input <summary.json> --replace-source`
   - production: `POST /admin/import/farmmap/crop-regions` with `X-Admin-Key`.
5. Query `/api/v1/map/farmmap/crop-regions?item_code=cabbage`.
6. Replace beta FarmMap/soil layer UI with a real source-labeled layer.

## Data Integrity

- If a FarmMap source only has land-use type but no crop, label it as land-use context, not crop area.
- If a crop alias is broad or ambiguous, set lower confidence.
- If area is missing, count parcels but do not claim hectares.
- If geometry is parcel-level, aggregate or simplify before public display.
