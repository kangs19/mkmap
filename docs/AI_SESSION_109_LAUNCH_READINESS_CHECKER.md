# AI Session 109 - Launch Readiness Checker

Date: 2026-07-06 KST

## What Changed

- Added `scripts/verify_launch_readiness.py`.
- The script checks launch-critical public pages and APIs without admin credentials or secrets.
- Rebuilt `legal/privacy.html` and `legal/terms.html` as readable Korean UTF-8 pages.
- Added the new checker to `scripts/run_smoke_suite.py` py_compile targets.

## What The Checker Verifies

- `/health` returns HTTP 200 and `env=production`.
- `/` contains the production app shell, legal links, signup consent checkbox, `terms_accepted` signup payload, map hover fallback code, and compact trend judgment code.
- `/privacy` and `/terms` return HTTP 200 with readable Korean legal content.
- `/sitemap.xml` includes `/privacy` and `/terms`.
- `POST /api/v1/auth/register` without `terms_accepted` returns `terms_required` before account creation.
- Invalid login returns HTTP 401 with Korean-facing message text.
- `/api/v1/map/weather`, `/api/v1/signals/today`, `/api/v1/dashboard/cards`, and `/api/v1/items/cabbage/forecast` are populated.

## Commands

Local syntax check:

```powershell
python -m py_compile scripts\verify_launch_readiness.py
```

Production launch check:

```powershell
python scripts\verify_launch_readiness.py --base-url https://mk-map.com --timeout-seconds 20
```

Machine-readable output only:

```powershell
python scripts\verify_launch_readiness.py --base-url https://mk-map.com --json-only
```

## Current Result

- Initial production run passed 10/11 checks.
- The only failure was that `/terms` did not contain the Korean service name `팜맵`.
- Fixed locally by rebuilding both legal pages in readable Korean.
- After deploy, rerun the production launch check. Expected result: 11/11.

## Notes For Next Agent

- Do not add admin-only checks to this script. It is intentionally safe to run without secrets.
- Keep data freshness checks light. Deep model quality belongs in model/backtest audit scripts.
- If this script fails after deployment, treat it as a release gate before opening public signup.
