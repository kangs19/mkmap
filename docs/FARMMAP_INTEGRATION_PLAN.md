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
   - CSV, GeoJSON, JSON, DBF, and ZIP-with-DBF are supported.
   - SHP geometry is not parsed yet, but the DBF attribute table inside a SHP ZIP can be audited directly.
2. Review detected fields/crops.
   - DBF field names are often short ASCII names, so use the provider column dictionary when available.
3. If crop and area fields exist, run a region-summary importer.
4. Import the summary:
   - local: `python scripts/import_farmmap_crop_region_summary.py --input <summary.json> --replace-source`
   - production: `POST /admin/import/farmmap/crop-regions` with `X-Admin-Key`.
5. Query `/api/v1/map/farmmap/crop-regions?item_code=cabbage`.
6. Replace beta FarmMap/soil layer UI with a real source-labeled layer.

## Verified Public Source: Gangwon

Official public source verified on 2026-07-05 KST:

- data.go.kr detail page: `https://www.data.go.kr/data/15104490/fileData.do`
- source title: `농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도`
- downloaded file: `농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도_20251231.zip`
- local raw path: `data/farmmap/raw/농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도_20251231.zip`
- file size: 203,035,902 bytes
- archive contents: 18 SHP/DBF city/county bundles, 736,009 DBF records
- verified fields: `CLSF_NM`, `CLSF_CD`, `STDG_CD`, `STDG_ADDR`, `PNU`, `AREA`, `SOURCE_NM`, `FLIGHT_YMD`, `UPDT_YMD`

Important finding: this Gangwon FarmMap source does not contain a crop or item name field. `CLSF_NM` is a land-use class, not a crop. Observed values are `밭`, `논`, `시설`, `과수`, and `비경지`. Therefore this source must be used as an agricultural land-use/parcel base layer and a regional farming capacity feature, not as direct crop-specific acreage.

Generated local audit and summary:

- audit: `data/farmmap/audits/gangwon_20251231_audit.json`
- land-use summary: `data/farmmap/summaries/gangwon_20251231_landuse_summary.json`
- summary output: 736,009 source rows -> 89 region/class rows, total 104,853.407179 ha
- class totals: 밭 67,180.66 ha, 논 30,319.39 ha, 시설 4,501.43 ha, 과수 2,766.52 ha, 비경지 85.41 ha

Because `data/` is local/raw-data storage, these outputs are not committed. Rebuild with:

```bash
python scripts/download_farmmap_source.py --province 강원특별자치도 --max-mb 250
python scripts/audit_farmmap_spatial_file.py --input data/farmmap/raw/농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도_20251231.zip --sample-rows 1800 --output data/farmmap/audits/gangwon_20251231_audit.json
python scripts/build_farmmap_landuse_region_summary.py --input data/farmmap/raw/농림수산식품교육문화정보원_팜맵공간정보_강원특별자치도_20251231.zip --output data/farmmap/summaries/gangwon_20251231_landuse_summary.json
```

## Data Integrity

- If a FarmMap source only has land-use type but no crop, label it as land-use context, not crop area.
- If a crop alias is broad or ambiguous, set lower confidence.
- If area is missing, count parcels but do not claim hectares.
- If geometry is parcel-level, aggregate or simplify before public display.
