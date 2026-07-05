# MK Map Production Readiness Audit

Date: 2026-07-05 KST

This document is the working checklist for moving MK Map from MVP to a public service that can safely accept members.

## Current Product Shape

- Core service: crop/region map, price forecasts, regional price context, market/weather signals, community/member features.
- Main production URL: `https://mk-map.com`
- Backend API: `https://mk-map.com/api/v1`
- API docs: `https://mk-map.com/docs`
- Repository: `https://github.com/kangs19/mkmap`

## Launchable Now

- General member signup/login API exists:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/me`
- Auth/community routes are exempt from the public API-key gate.
- Price forecast endpoints are live and smoke-tested.
- Regional map price endpoint is live and now distinguishes observed values from unavailable values.
- Price forecast UI now shows the regional wholesale-market basis:
  - real regional market names when the API returns market rows.
  - representative fallback market only when measured market rows are missing.
- Non-working map layers are no longer shown as normal active controls:
  - pest risk map is marked `BETA`.
  - soil map is marked `BETA`.
- Unwired notification button is hidden until the notification backend is complete.

## Not Ready For Broad Public Marketing

- Farmer/trader role registration requires phone verification. Confirm a real SMS provider and production verification flow before advertising those roles.
- Legal pages are still needed:
  - privacy policy.
  - terms of service.
  - marketing/push consent.
  - account deletion and data-retention policy.
- Import/substitute supply features are not fully wired to verified data.
- Pest, soil, and some climate-event overlays need real collectors or should stay explicitly beta.
- FarmMap now has storage/API/audit scaffolding, but still needs official source-file import before enabling the public layer.
- KMA and other public API collectors need scheduled monitoring and retry/error reporting.
- Production observability should be reviewed:
  - Railway deploy status.
  - daily pipeline success/failure notification.
  - DB backup and restore procedure.
  - admin key rotation procedure.

## Data Integrity Rules

- Do not show arbitrary numeric values as if they are measured.
- If a value is modeled, label it as model/forecast.
- If a value is representative fallback, label it as representative.
- If a value cannot be sourced, hide it or show unavailable.
- Do not use simple multipliers such as retail equals wholesale times a fixed ratio unless the model and source are documented.

## UI Rules

- Map is the primary product surface.
- Left side: crop, period, and map filter controls.
- Center: map with region, market, price, and climate overlays.
- Right side: selected-region detail with tabs.
- Price forecast tab should contain:
  - current average price.
  - compact horizon labels.
  - increase/decrease reason analysis.
  - market basis.
  - risk summary.
- Cultivation/market tab should contain crop metadata, production/shipment/market information, and verified regional context.
- Disable or mark beta any control that is not connected to real data.

## Next Recommended Work

1. Production auth acceptance test:
   - register one disposable general user.
   - login.
   - call `/api/v1/auth/me` with the returned token.
2. Add footer/modal links for privacy policy and terms.
3. Add a signup/login entry point in the main UI if it is not visible enough.
4. Add pipeline status/admin health UI for data freshness.
5. Replace static representative market fallback with a DB-backed market-influence calculation from agromarket/origin/auction data.
6. Import one official FarmMap source file through the new audit and summary pipeline.
7. Keep pest and soil overlays beta until collectors and source labels are complete.
