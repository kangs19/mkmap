# AI Session 114 - Robust Map Hover Popup

Date: 2026-07-06

## User Issue

The user reported again that hovering over map regions still did not show the popup view.

## Cause

The map already had several hover paths:

- Leaflet path events
- DOM events on SVG paths and marker icons
- Leaflet-native tooltips
- a map-level fallback using `elementsFromPoint`

However, these were still dependent on event order and whether the exact SVG/marker node carried a handler. In some browser/layer states, the hover target could miss the custom handler or show only a native title/tooltip inconsistently.

## Changes

- Forced pointer events on `.leaflet-interactive` and `.leaflet-marker-icon`.
- Added `data-tooltip` and `data-fm-tooltip-html` to bound SVG paths.
- Strengthened `setupMapHoverFallback()`:
  - Uses delegated document-level `mouseover` and `mousemove`.
  - Finds `#map .leaflet-marker-icon` and `#map .leaflet-interactive` directly from the event target.
  - Falls back to `data-fm-tooltip-html`, `data-tooltip`, `title`, SVG `<title>`, or `aria-label`.
  - Keeps `#map-tooltip` visible even if Leaflet's own event chain does not fire.
  - Cleans up tooltip state when leaving the map.
- Added the delegated hover fragment to `scripts/verify_launch_readiness.py` so the launch checker catches accidental removal.

## QA

- `python scripts\audit_frontend_launch_ui.py` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.
- Local browser QA:
  - Moved the pointer onto a province SVG path.
  - `#map-tooltip` displayed with region/crop details.
  - Moved the pointer onto a crop marker pin.
  - `#map-tooltip` remained visible with region/crop details.

## Remaining Notes

- Local QA DB has sparse regional price data, so some hover card price fields can show "가격 수집 중" locally.
- Production regional price availability is covered by the `regional_prices` launch readiness check.

