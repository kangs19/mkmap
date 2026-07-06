# Session 92 - Auth Beta QA

Date: 2026-07-06

## Goal

Continue beta-tester style launch QA after the mobile pass, focusing on member/auth flows that can leak confusing technical messages to public users.

## What Was Checked

- Production invalid login response.
- Production invalid email registration response.
- Production farmer signup without phone verification response.
- Production invalid phone-number response.
- Local backend regression coverage for auth error messages.

No real SMS send was triggered during this QA pass.

## Finding

Most production auth errors already returned Korean messages, but phone verification input validation could still fall back to FastAPI/Pydantic default English messages before the route-level Korean error handling ran.

That would be confusing for older users and does not match the public UX tone.

## Changes

- `backend/app/routers/auth_user.py`
  - Phone send/verify request models now accept raw strings first.
  - Route handlers normalize and validate phone/code values themselves.
  - Short or invalid phone numbers now return:
    - `올바른 휴대폰 번호를 입력해 주세요.`
  - Invalid verification code format now returns:
    - `인증번호를 다시 확인해 주세요.`
  - `/api/v1/auth/me` now includes the public Korean message:
    - `로그인이 필요합니다.`

- `backend/tests/test_api.py`
  - Added regression coverage for public Korean auth error messages:
    - invalid login
    - missing login session
    - farmer signup without phone verification
    - invalid phone send
    - invalid phone verify

## Validation

- `PYTHONPATH=backend python -m pytest backend/tests/test_api.py -q`
  - Passed: 38 tests
- `python scripts/run_smoke_suite.py --timeout-seconds 300`
  - Passed

## Launch Readiness Impact

Member signup/login is safer to expose to beta users because obvious failure cases now stay in Korean and avoid backend validation jargon.

Farmer/trader signup still depends on real SMS provider readiness before those roles should be advertised broadly.

## Next QA Slice

1. Browser-test the auth modal on production after deploy.
2. Check layer combinations on desktop and mobile:
   - price forecast
   - weather
   - wholesale market pins
   - FarmMap land-use
3. Continue the 100-piece launch QA checklist in `docs/UX_FUNCTION_AUDIT_100.md`.
