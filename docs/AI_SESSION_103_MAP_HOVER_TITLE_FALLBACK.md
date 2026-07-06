# Session 103 - Map Hover Title Fallback

Date: 2026-07-06

## Goal

Fix the recurring issue where hovering over map regions still does not show the custom popup card for some users.

## Changed Files

- `index.html`

## What Changed

- Added a final hover fallback that does not depend on the richer Leaflet handler map.
- `findHoverTargetAtPoint` now accepts a target when it has:
  - registered tooltip handlers,
  - `__fmTooltipHandlers`,
  - or just a usable `title` / `data-tooltip` / `aria-label`.
- Added fallback helpers:
  - `mapFallbackTitle`
  - `mapFallbackTooltipHtml`
  - `fallbackTooltipHandlersFor`
- If rich handlers are unavailable, the app now builds a simple custom popup from the SVG path `title` or marker `data-tooltip`.
- This means province/city SVG paths with titles such as `서울특별시 · 배추 대표 산지 검증 데이터 부족` still show a visible popup instead of relying only on the browser native title.

## Why

Production inspection showed:

- `.leaflet-interactive` SVG paths existed,
- `title` text existed,
- `data-fm-dom-bound="1"` existed,
- but the rich handler object was not reliably visible/available in the browser context.

The new fallback uses the title text as the minimum viable popup source, so hover information still appears even when the richer event binding is brittle.

## Verification

- `git diff --check` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Production inspection before the fix confirmed path titles existed but the custom tooltip did not show.

## Follow-Up

- After deploy, manually test:
  - national province hover,
  - city/county hover after drilling into a province,
  - marker hover,
  - inactive/gray region hover.
- If custom popup still fails, the next step is replacing the Leaflet SVG hover surface with a single map-level pointer tracker that always reads `elementsFromPoint` and uses raw `title` text without event listener dependency.
