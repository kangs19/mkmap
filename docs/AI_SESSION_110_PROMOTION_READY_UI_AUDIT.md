# AI Session 110 - Promotion-Ready UI Audit

Date: 2026-07-06 KST

## Goal

The user said MK-MAP should not be treated as a prototype and may be promoted directly. The working standard was raised from MVP smoke testing to public-user launch QA.

## Changes

- Removed critical frontend runtime dependency on external CDN files:
  - Leaflet CSS/JS now load from `/static/vendor/leaflet/`.
  - Chart.js now loads from `/static/vendor/chartjs/`.
  - Google Fonts dependency was removed; the app now falls back to Korean system fonts such as `Malgun Gothic`.
- Added local vendor assets under `map_viewer/static/vendor/`.
- Removed disabled beta layer rows from the left map filter:
  - `병해충 위험`
  - `토양 정보`
- Replaced several browser `alert()` messages with the app's existing toast notification.
- Added `scripts/audit_frontend_launch_ui.py`.
- Added the frontend audit to `scripts/run_smoke_suite.py`.
- Extended `scripts/verify_launch_readiness.py` so production checks verify:
  - local Leaflet/Chart references in the home shell,
  - local vendor static files,
  - map boundary static files.

## Frontend Audit Coverage

`scripts/audit_frontend_launch_ui.py` checks:

- every `onclick` function name exists in the page script,
- duplicate HTML ids,
- critical external runtime dependencies,
- disabled beta controls left visible in the launch UI.

Current result:

```json
{
  "ok": true,
  "missing_onclick_count": 0,
  "duplicate_id_count": 0,
  "critical_external_dependency_count": 0,
  "disabled_beta_control_count": 0
}
```

## Why This Matters

For public promotion, the map must not fail just because a user's network blocks `unpkg.com`, `jsdelivr.net`, or Google Fonts. Also, visible disabled beta controls make the service feel unfinished, so unfinished layers should stay out of the main launch UI until data is actually wired.

## Commands

```powershell
python scripts\audit_frontend_launch_ui.py
python scripts\run_smoke_suite.py --timeout-seconds 120
python scripts\verify_launch_readiness.py --base-url https://mk-map.com --timeout-seconds 30
```

## Remaining Watch Items

- `www.mk-map.com` still needs a proper Railway custom domain/certificate or redirect.
- The map still uses external map tiles for base map imagery. If tile providers are blocked, GeoJSON crop regions should still draw over the map background, but full offline tile hosting is not yet implemented.
