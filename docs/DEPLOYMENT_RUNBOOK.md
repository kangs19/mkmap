# Deployment Runbook

This runbook keeps production setup details in one place without storing real secrets.

## Runtime

- Public domain: `https://mk-map.com`
- Backend docs: `https://mk-map.com/docs`
- Deployment target: Railway
- Start command: `/app/start.sh`
- Health check: `/health`
- App process: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8100} --workers 1`

Railway currently sets:

- `APP_ENV=production`
- `PORT=8100`

## Required Secrets

Set these in Railway variables, not in Git:

- `DATABASE_URL`
- `ADMIN_KEY`
- `DATA_GO_KR_API_KEY`
- `KAMIS_API_KEY`
- `KOSIS_API_KEY`

Optional or service-specific variables:

- `KAMIS_CERT_ID`
- `DISCORD_WEBHOOK_URL`
- `REQUIRE_API_KEY`
- KAMIS endpoint variables from `.env.example`
- KOSIS endpoint variables from `.env.example`
- KMA/data.go.kr endpoint variables from `.env.example`

Use `.env.example` as the complete variable inventory. Keep local `.env` and Railway variables synchronized by variable name, but never copy real values into documentation or commits.

## Scheduler

The FastAPI lifespan starts `backend/app/scheduler.py`.

- Timezone: `Asia/Seoul`
- Daily job: metadata pipeline at `06:00` KST
- Pipeline command equivalent: `python scripts/run_meta_pipeline.py --date YYYY-MM-DD`
- After success, the scheduler clears cached signal/report responses and sends a Discord daily report if `DISCORD_WEBHOOK_URL` is configured.
- On fresh deployment, `_auto_recover()` checks whether today's `region_signals` and `forecasts` exist. If they are missing, it runs the metadata pipeline once after startup.

## Deployment Checklist

1. Confirm Railway variables include every required secret above.
2. Confirm `DATABASE_URL` points to the intended production database.
3. Confirm `ADMIN_KEY` in Railway matches the key used in `/admin/ui`.
4. Deploy from the `main` branch after GitHub CI succeeds.
5. Open `/health` and check `status: ok` plus `scheduler: true`.
6. Open `/api/v1/admin/status` with `X-Admin-Key` and confirm data freshness, scheduler jobs, and API diagnostics.
7. If today's forecasts are missing, run the metadata pipeline from Admin UI or wait for auto-recover/scheduler.

## Useful Checks

Local:

```powershell
python scripts\check_env_status.py
python scripts\run_smoke_suite.py --timeout-seconds 90
cd backend
$env:DATABASE_URL='sqlite+aiosqlite:///./test_agri.db'
$env:ADMIN_KEY='test-admin-key'
python -m pytest tests\test_pipeline.py tests\test_api.py -q
```

Production:

```powershell
curl https://mk-map.com/health
curl https://mk-map.com/api/v1/dashboard/cards
curl https://mk-map.com/api/v1/alerts/high-risk
```

Admin endpoints require `X-Admin-Key`.

## Known Provider Notes

- KMA weather alert may return provider-side `DB_ERROR`; retry diagnostics after the provider clears it.
- KMA crop-weather data can have provider delay. Admin freshness distinguishes fresh, provider delay, fallback date, and missing data.
- Generated files under `data/` are not committed. Production should rely on scheduled pipeline outputs and database imports.
