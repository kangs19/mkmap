# Session 69 - FarmMap Land-Use Layer Explanation (2026-07-05)

## User Problem

When `팜맵 농지분류` is enabled, a whole province such as Gangwon can be colored.
That can look like the entire province is farmland, which is not what the data means.

## Meaning Of The Layer

The FarmMap layer is an administrative-area summary overlay.

- Color = the dominant FarmMap land-use class within the selected administrative area.
- Opacity/intensity = the scale of aggregated FarmMap land-use area.
- The filled polygon is the 시도/시군구 boundary, not the actual parcel geometry.
- A colored province does not mean the whole province is farmland.
- This is not crop-specific acreage.

## Implementation

Updated `index.html`.

- Added a FarmMap-specific explanation box under the map layer controls.
- The box appears only when `팜맵 농지분류` is enabled.
- Expanded FarmMap hover copy:
  - explains color = representative land-use class.
  - explains intensity = aggregated area scale.
  - states that the full administrative polygon is a summary display, not actual farmland coverage.
  - states that FarmMap land-use is not crop acreage.
- Added the same clarification to the right detail panel FarmMap section.
- Changed FarmMap polygon styling to a dashed boundary so it reads more like a summary overlay than a literal coverage fill.

## Verification

- `cd backend; python -m pytest tests\test_api.py -q` passed: 33 tests.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Static browser check at `http://127.0.0.1:8021/` confirmed:
  - FarmMap note is hidden by default.
  - FarmMap note appears after enabling the layer.
  - no captured runtime errors.
