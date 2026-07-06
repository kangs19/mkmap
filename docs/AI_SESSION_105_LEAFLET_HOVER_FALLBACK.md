# AI Session 105 - Leaflet Hover Tooltip Fallback

Date: 2026-07-06

## Goal

The user repeatedly reported that map hover popups still did not appear over regions, especially after drilling into lower map levels. Previous custom DOM/title fallbacks existed, but user-visible hover still needed a stronger fallback.

## Changed

- Added a Leaflet-native fallback tooltip style:
  - `.fm-hover-leaflet-tooltip`
  - `.fm-native-tip-title`
  - `.fm-native-tip-line`
- Added helper functions:
  - `mapLeafletTooltipHtml(title)`
  - `bindLayerHoverTooltip(layer,title)`
- Bound Leaflet tooltips to:
  - province SVG paths;
  - province summary pins;
  - city/county SVG paths after drilldown;
  - city/county crop pins.

## Why This Approach

The existing custom popup remains in place. The new Leaflet tooltip is an additional safety layer: if DOM mouse handlers, native browser titles, or the custom fixed tooltip path fail, Leaflet itself can still show a hover card for map geometry and markers.

## Validation

- `git diff --check` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Local static server loaded `index.html` and showed province paths carrying bound metadata.

## Next QA

- After deploy, manually verify `https://mk-map.com` in a normal browser or cleared-profile browser because the Codex in-app browser can retain an old `mkmapcom.wordpress.com` redirect failure.
- Check both levels:
  - national map province hover;
  - province drilldown city/county hover.
