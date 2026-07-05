# AI Session 74 - FarmMap Legend And Crop Overlap Hatch

Date: `2026-07-05`

## User Feedback

When the FarmMap landuse layer and crop layer overlap, plain colors are hard to understand. The FarmMap note also explains the concept, but it does not show which color means paddy, field, greenhouse, orchard, or other landuse.

## Change Made

- Added a FarmMap landuse palette:
  - paddy/rice,
  - field/upland,
  - greenhouse/facility,
  - orchard,
  - other.
- Added a visible FarmMap legend inside the layer note.
- Added a hatch legend item:
  - hatch means the selected crop region and FarmMap landuse summary overlap.
- Added SVG hatch pattern helpers for FarmMap overlap rendering.
- Changed map styling logic:
  - crop-active + FarmMap-active regions keep the crop/price/production base color,
  - a FarmMap-colored hatch overlay is drawn above them,
  - FarmMap-only regions still use the solid FarmMap landuse color.

## Files Changed

- `index.html`

## Verification

- `python scripts\check_text_encoding_health.py`: passed.
- `python -m pytest tests\test_api.py -q`: passed, `33 passed`.
- `python scripts\run_smoke_suite.py --timeout-seconds 300`: passed.
- Browser check on `http://127.0.0.1:8028/index.html`:
  - FarmMap note displays,
  - FarmMap legend text is present,
  - hatch legend text is present,
  - no current-page browser errors were observed.

## Note

On a static local server, FarmMap API data is not available, so actual hatch paths cannot be produced there. The hatch overlay is wired to render after `/api/v1/map/farmmap/landuse-regions` returns data in the full app/backend environment.
