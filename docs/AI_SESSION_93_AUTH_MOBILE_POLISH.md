# Session 93 - Auth Mobile Polish

Date: 2026-07-06

## Goal

Follow up on the auth beta QA by checking the actual mobile modal experience, not only API responses.

## Finding

The login modal fit inside a 390 px mobile viewport and had no horizontal overflow, but the email/password fields were only about 37 px high.

That is usable, but slightly small for the older farmer/market-user audience.

The browser tab title was also still English:

- `FARM MAP - Price Risk Signal Engine`

## Changes

- `index.html`
  - Browser title changed to `MK-MAP 농산물 가격 예측`.
  - Mobile auth inputs/selects now have a 44 px minimum height.
  - Mobile auth primary/SMS buttons now have a 44 px minimum height.
  - Auth error/helper messages are larger on mobile.

## Browser QA

Local mobile viewport: 390 x 844

- No horizontal overflow.
- Login modal remained inside viewport.
- Email input height: 44 px.
- Password input height: 44 px.
- Primary button height: 44 px.
- Page title: `MK-MAP 농산물 가격 예측`.
- Console error buffer: empty.

## Next QA Slice

Continue the launch QA checklist:

1. Layer combinations on desktop and mobile.
2. Hover tooltip behavior after region drilldown.
3. Right-panel tab content density and usefulness.
4. Statistics/dashboard Korean copy and ranking clarity.
