# AI Session 115 - Fail-Safe Price Map Overlay

Date: 2026-07-06

## User Issue

The user reported that the live map again showed only the base map after changing map filter options. The price prediction layer did not show crop regions or price information, and hover popups were still unreliable from the user's view.

## Cause

The map now loads a lightweight province GeoJSON, but the first visible price map still depended on the Leaflet boundary render chain. A static safety layer had been introduced, but `drawProvinces()` removed it at the start of rendering. If the GeoJSON render then stalled or failed partway, the safety layer was already gone and the user saw a blank base map.

The original static overlay also depended on richer map helper functions. If any of those helpers failed during early boot, the whole fallback could fail too.

## Changes

- Rebuilt `renderStaticMapOverlay()` as an independent DOM overlay.
- It now reads only minimal safe inputs:
  - current item,
  - regional price cache when available,
  - national price fallback,
  - static province centers.
- It no longer depends on `makeHoverCard()`, `regionalPriceColor()`, or other Leaflet helper paths that may fail during early map boot.
- It renders province-level round price bubbles directly inside `#map` with:
  - region name,
  - current wholesale price or `확인중`,
  - color based on regional deviation from national average.
- Each bubble has direct custom `mouseenter`, `mousemove`, `mouseleave`, and `click` handlers for `#map-tooltip`.
- `drawProvinces()` no longer removes the static overlay before drawing. It removes it only after actual map paths or pins exist.

## QA

- `python scripts\audit_frontend_launch_ui.py` passed.
- `git diff --check` passed.
- Local FastAPI browser QA on `http://127.0.0.1:8107/`:
  - loading overlay hidden,
  - 17 Leaflet province paths rendered,
  - 4 price pins rendered,
  - first visible pin contained price prediction text,
  - moving the mouse over the pin displayed `#map-tooltip`.
- Follow-up fix after production refresh:
  - the static overlay was briefly visible, then disappeared because the readiness check counted `.fm-static-map-bubble` as a real `.region-pin`,
  - the readiness selector now excludes `.fm-static-map-bubble`,
  - if real Leaflet paths or non-static pins are still absent after `drawProvinces()`, `renderStaticMapOverlay("province_render_empty")` is called again.
- Local FastAPI browser QA on `http://127.0.0.1:8108/` after the follow-up fix:
  - after a 9 second wait, the map still had 17 paths and 4 real pins,
  - hover popup displayed correctly on a visible price pin.
- Follow-up after user clarified the desired map is the filled administrative-region map, not round fallback bubbles:
  - the light province GeoJSON can contain mojibake in `properties.name`,
  - `getSido()` now resolves province identity from the stable numeric province `code` first,
  - name-based lookup remains only as a fallback,
  - local browser QA confirmed the filled province paths render again with 17 interactive paths, 4 real price label pins, and no static round overlay.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.

## Next Check

After deployment, verify production with a fresh cache-busting URL:

- `https://mk-map.com/?qa=<commit>`
- Confirm either:
  - `#fm-static-map-overlay .fm-static-map-bubble` exists quickly, or
  - real Leaflet province paths/pins exist.
- Confirm hovering a visible map region or price pin displays `#map-tooltip`.
