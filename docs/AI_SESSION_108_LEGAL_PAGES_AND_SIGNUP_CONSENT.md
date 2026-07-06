# AI Session 108 - Legal Pages and Signup Consent

Date: 2026-07-06

## Goal

Prepare launch-required legal surfaces requested by the user: privacy policy and terms of service. Also connect them to signup so new members must consent before registration.

## External Reference

Checked current Korean privacy-policy guidance before drafting:

- 개인정보보호위원회 / 개인정보포털 `2026 개인정보 처리방침 작성지침`
- Key implementation implication: privacy policy should clearly disclose processing purpose, items, retention, third-party provision, outsourcing, destruction, data-subject rights, security measures, automatic collection, responsible contact, remedy channels, and changes.

## Changed

- Added `legal/privacy.html`
  - Korean 개인정보처리방침 draft.
  - Covers collected items, purposes, retention, third-party provision, outsourcing, destruction, user rights, security, cookies/storage, contact, remedy, and changes.
- Added `legal/terms.html`
  - Korean 이용약관 draft.
  - Covers service nature, account rules, prediction disclaimer, community rules, data/IP, service interruption, liability limits, privacy, and disputes.
- Added FastAPI routes:
  - `/privacy`, `/privacy.html`
  - `/terms`, `/terms.html`
- Added legal URLs to `sitemap.xml`.
- Added frontend legal links:
  - default right-panel bottom;
  - auth modal bottom;
  - signup consent block.
- Signup now requires legal consent on both sides:
  - frontend blocks if unchecked;
  - backend `RegisterIn.terms_accepted` must be true.
- Updated backend auth test to preserve the existing `phone_required` case under the new terms gate.

## Important Notes

- The pages are launch-ready drafts, not final legal advice.
- `privacy@mk-map.com` is shown as the privacy contact with a note that receiving must be configured before production launch.
- Real business/operator name, contact, SMS provider, hosting/vendor details, and retention periods should be finalized before public member acquisition.

## Validation

- `git diff --check` passed.
- `python -m py_compile backend\app\main.py backend\app\routers\auth_user.py` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- `$env:PYTHONPATH='backend'; pytest backend\tests\test_api.py -q` passed: 38 tests.

## Next Work

- Verify `/privacy` and `/terms` on production after Railway deploy.
- Add final operator contact details.
- Continue release QA: signup/login, hover, detail tabs, mobile readability, and anomaly price checks.
