# AI Session 114 - Robust Map Hover Popup

Date: 2026-07-06

## User Issue

The user reported again that hovering over map regions still did not show the popup view.
After the first robustness patch, the user also reported that the map looked wrong:

- selecting map filter options could leave the `가격 예측` layer without crop regions/pins,
- a black native-looking tooltip appeared over the map,
- a narrow white tooltip/card could appear instead of the intended custom popup.

## Cause

The map already had several hover paths:

- Leaflet path events
- DOM events on SVG paths and marker icons
- Leaflet-native tooltips
- browser-native `title` attributes and SVG `<title>` children
- a CSS `region-pin[data-tooltip]::after` pseudo tooltip
- a map-level fallback using `elementsFromPoint`

However, these were still dependent on event order and whether the exact SVG/marker node carried a handler. In some browser/layer states, the hover target could miss the custom handler or show only a native title/tooltip inconsistently.

## Changes

- Forced pointer events on `.leaflet-interactive` and `.leaflet-marker-icon`.
- Added `data-tooltip` and `data-fm-tooltip-html` to bound SVG paths.
- Removed browser-native tooltip sources from crop map layers:
  - no `title` attribute on SVG paths or region pins,
  - no SVG `<title>` children on bound crop paths,
  - no Leaflet `bindTooltip()` for crop regions/pins,
  - disabled the old black CSS pseudo tooltip for `.region-pin`.
- Bound direct custom tooltip events to Leaflet marker icons and their `.region-pin` children, so marker hover does not depend only on map-level bubbling.
- Strengthened `setupMapHoverFallback()`:
  - Uses delegated document-level `mouseover` and `mousemove`.
  - Finds `#map .region-pin`, `#map .leaflet-marker-icon`, and `#map .leaflet-interactive` directly from the event target.
  - Falls back to `data-fm-tooltip-html`, `data-tooltip`, or `aria-label`.
  - Keeps `#map-tooltip` visible even if Leaflet's own event chain does not fire.
  - Cleans up tooltip state when leaving the map.
- Made `#map-tooltip` width stable (`min(390px, calc(100vw - 24px))`) so long region text does not collapse into a narrow vertical card.
- Hardened `가격 예측`/`재배 면적` layer toggles:
  - they remain mutually exclusive,
  - one base crop map mode is always active,
  - switching back to `가격 예측` refreshes regional prices and redraws crop regions/pins.
- Added `map_viewer/static/skorea_provinces_light.json`:
  - the full province GeoJSON is about 7.5MB and could leave production waiting at the map loading overlay,
  - the light province file is about 0.52MB,
  - the first nationwide price/production map now loads the light file, while the full source file remains in the repo.
- Added `drawProvinceFallbackMap()`:
  - if province GeoJSON rendering throws, the map no longer stays blank,
  - if GeoJSON loading stays pending for more than 4.5 seconds, the fallback map is drawn automatically,
  - it draws price-colored circle regions from `SIDO_CENTER`, item metadata, and regional price data,
  - it keeps custom hover popups and click-through to the top available city detail.
- Added the light province asset to launch readiness static-asset checks.
- Added the delegated hover fragment to `scripts/verify_launch_readiness.py` so the launch checker catches accidental removal.

## QA

- `python scripts\audit_frontend_launch_ui.py` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.
- Local browser QA:
  - Moved the pointer onto a province SVG path.
  - `#map-tooltip` displayed with region/crop details.
  - Moved the pointer onto a crop marker pin.
  - `#map-tooltip` remained visible with region/crop details.
- Follow-up Local FastAPI browser QA:
  - default `가격 예측` state rendered 17 crop paths and 4 price pins,
  - crop map layers had `title` count 0 and Leaflet tooltip count 0,
  - crop pin hover displayed `#map-tooltip` at 390px width,
  - toggling `재배 면적 -> 가격 예측 -> 팜맵 on/off` kept 17 crop paths and 4 pins visible.
- Production browser QA before the light file change showed the app still waiting at "지도 데이터 로딩 중" with 0 paths/pins, so the light province file is a launch-critical performance fix rather than only a polish item.
- Local browser QA after fallback wiring showed loading hidden, 17 crop paths, 4 price pins, no native `title`, and no Leaflet tooltip.

## Remaining Notes

- Local QA DB has sparse regional price data, so some hover card price fields can show "가격 수집 중" locally.
- Production regional price availability is covered by the `regional_prices` launch readiness check.
