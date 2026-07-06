# AI Session 116 - Crop Polygon Map Restore

Date: 2026-07-06
Commit: `9691379 Fix crop polygon map rendering`

## Problem

The live map was showing either an empty base map or emergency oval/circle fallback shapes across the country. This was not acceptable because the intended UX is:

- show only verified crop growing regions,
- draw real administrative polygon areas on the map,
- place compact price/prediction labels on those crop polygons,
- keep hover popups available on both polygon and label targets.

For cabbage, the expected restored state is province polygons such as Gangwon, Chungbuk, Jeonnam, and Jeju, with price labels on top of the regions.

## Root Cause

Two frontend fail-safe changes were masking the real issue.

1. `isHorizonBlocked(itemCode, days)` could recursively call itself through the nearest horizon branch. In production this produced `RangeError: Maximum call stack size exceeded` while the map was rendering.
2. When the normal Leaflet GeoJSON render path failed or appeared delayed, the page rendered emergency static SVG shapes. Those shapes were approximate ovals/blobs and did not match real crop areas.

## Fix

Updated `index.html`:

- Removed the recursive `isHorizonBlocked(itemCode, nearest.days)` call and now directly checks the nearest row with `isPublicForecastHorizon(nearest.row)`.
- Removed the normal-load timeout path that rendered `renderEmergencyProvinceAreaOverlay`.
- Stopped replacing an empty province render with `renderStaticProvinceShapeOverlay`.
- Cleared any old static overlay before normal province drawing.
- Made non-crop provinces transparent in the crop price layer so only active crop regions are visually emphasized.

## Verification

Local checks:

- `git diff --check` passed.
- `python scripts\audit_frontend_launch_ui.py` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.

Production check on `https://mk-map.com/?qa=9691379`:

- `leafletPaths`: 4
- `activeLeafletPaths`: 4
- `markerPins`: 4
- `shapeOverlay`: false
- `shapePaths`: 0
- `fallbackBubbles`: 0
- visible labels included:
  - Gangwon cabbage price/prediction label
  - Chungbuk cabbage price/prediction label
  - Jeonnam cabbage price/prediction label
  - Jeju cabbage price/prediction label
- Hover popup worked on the Gangwon label/polygon area.

## Important Follow-Up Rule

Do not reintroduce nationwide circle/oval fallback shapes for the public map. If GeoJSON rendering fails, fix the render path or show a clear loading/error state. The user's desired map surface is real administrative polygons over verified crop regions, not symbolic national bubbles.

## Next Work

- Continue checking lower map levels after province click so city/county polygons also keep hover behavior.
- Review the left layer filters so `재배 면적`, `가격 예측`, `기상 정보`, and `팜맵 농지분류` can be combined intentionally without hiding the crop polygon layer.
- Continue removing explanatory filler text and replace it with short AI judgment sentences based on the displayed data.
