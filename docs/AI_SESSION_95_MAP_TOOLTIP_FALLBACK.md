# Session 95 - Map Tooltip Fallback

Date: 2026-07-06

## Goal

Continue launch QA on the map hover issue and add a simpler fallback that does not depend only on custom JavaScript hover events.

## Changes

- `index.html`
  - Region pins now carry both `title` and `data-tooltip`.
  - Added CSS-only pin tooltip using `.region-pin[data-tooltip]:hover::after`.
  - SVG map paths now receive `title`, `aria-label`, and an SVG `<title>` child when DOM hover handlers bind.
  - Province path title includes crop name, region readiness, city count, and available price summary.
  - City path title includes crop name and available price summary.

## Why

The custom floating `#map-tooltip` still depends on browser event delivery through Leaflet/SVG/marker layers.

This fallback gives users useful hover information even when the custom card does not fire, and improves accessibility for screen readers and native browser tooltips.

## Validation

Local desktop viewport: 1280 x 720

- CSS hover rule for `.region-pin[data-tooltip]:hover::after` was present.
- SVG map path had `title` and SVG `<title>` content.
- Console error buffer was empty.

Production validation after deploy should confirm:

- First visible `.region-pin` has a non-empty `data-tooltip`.
- First visible `.region-pin` has a non-empty `title`.
- A visible map path has a non-empty `title`.

## Next QA Slice

1. Confirm production pin `data-tooltip` after deploy.
2. Continue city drilldown hover QA with a real mouse if possible.
3. If custom floating tooltip still feels unreliable, replace it with a single delegated DOM tooltip driven only by `elementsFromPoint` and `data-tooltip`.
