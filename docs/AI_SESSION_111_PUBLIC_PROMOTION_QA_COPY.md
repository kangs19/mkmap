# AI Session 111 - Public Promotion QA Copy

Date: 2026-07-06

## Goal

Treat MK-MAP as a public service ready for promotion, not as a prototype, and remove launch-risk wording or brittle UI behavior that would weaken user trust.

## Changes

- Added a frontend guard for unknown item codes returned by `/api/v1/signals/today`.
  - Before: a stray or test item code could trigger `Cannot convert undefined or null to object` and interrupt live-data rendering.
  - After: unknown item signals are skipped with a console warning, while registered crops continue rendering.
- Replaced public fallback copy that said the map was using sample data.
  - New copy says the app is checking today's prediction signal and showing the map from secured cultivation/price references first.
- Removed "beta operation", "beta feature", and "public draft" wording from `/terms`.
  - The legal page now reads like an active service document while still preserving prediction/liability limits.
- Extended `scripts/audit_frontend_launch_ui.py`.
  - It now fails if public launch copy reintroduces "샘플 데이터", "프로토타입", "prototype", "베타 운영", "베타 기능", or "공개 초안".

## QA

- `python scripts\audit_frontend_launch_ui.py` passed.
- `python -m py_compile scripts\audit_frontend_launch_ui.py scripts\verify_launch_readiness.py scripts\run_smoke_suite.py` passed.
- `git diff --check` passed with only CRLF working-copy warnings.
- `python scripts\run_smoke_suite.py --timeout-seconds 120` passed.
- `python scripts\verify_launch_readiness.py --base-url https://mk-map.com --timeout-seconds 30 --json-only` passed 12/12.
- Browser QA on local server:
  - Map rendered with Leaflet tiles, province boundaries, and crop pins.
  - Province-level hover popup appeared.
  - Drilldown city-level hover popup appeared.
  - Public fallback copy no longer contained "샘플" or "베타".

## Remaining Launch Risk

- `https://mk-map.com` is launch-ready by the current checker.
- `https://www.mk-map.com` still has a certificate/hostname mismatch. If users may type `www.mk-map.com`, configure the Railway custom domain/DNS or redirect before broad promotion.

