# Session 94 - Map Hover QA

Date: 2026-07-06

## Goal

Continue beta launch QA on a repeated user complaint: map hover cards did not appear after moving into map regions, especially after drilldown.

## Finding

The map had both Leaflet event handlers and a DOM fallback for hover cards, but a stale DOM-bound marker could remain on SVG paths/marker icons without a live tooltip handler object.

When that happened, redraw/drilldown could skip rebinding because the element still had:

- `data-fm-dom-bound="1"`

but no usable handler reference.

## Change

- `index.html`
  - `bindMarkerDomEvents(...)` and `bindPathDomEvents(...)` now rebind when the DOM node has a stale bound flag but no stored tooltip handler.
  - This keeps hover cards active after map redraw, layer changes, and province/city drilldown.
  - The map hover fallback now also listens in document capture phase for `mousemove`, `pointermove`, `mouseover`, and `pointerover`.
  - This avoids relying only on Leaflet/SVG event bubbling when a path or marker swallows the event before it reaches `#map`.
  - Hover fallback now checks both the WeakMap registry and the DOM node's stored handler reference.

## Local Browser QA

Local desktop viewport: 1280 x 720

- Hovering a visible map path showed `#map-tooltip`.
- Capture-phase fallback was present in the loaded HTML.
- DOM-node handler fallback was present in the loaded HTML.
- Tooltip stayed within viewport bounds.
- Console error buffer was empty.

The local static server does not have the production API data attached, so the full active-region drilldown scenario must be confirmed again on production after deploy.

## Next QA Slice

1. Deploy and confirm production province hover.
2. Confirm production province click → city-level hover.
3. Confirm selected city detail does not leave a stuck tooltip.
4. Continue layer-combination QA.
