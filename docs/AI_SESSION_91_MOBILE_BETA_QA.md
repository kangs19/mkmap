# AI Session 91 - Mobile Beta QA

Date: 2026-07-06 KST

## Goal

Continue beta testing as a user and fix the next launch-risk area: small-screen and mobile usability.

The desktop map worked, but the layout used fixed desktop widths:

- left sidebar: 200px
- right detail panel: 720px
- map between them

That is fine on desktop, but it can crush the map and make the app unusable on phones.

## Changed Files

- `index.html`
- `docs/session_91_mobile_qa_screenshot.png`

## Changes

Added responsive CSS for breakpoints below 980px and 560px.

Mobile behavior:

- Header wraps into usable rows.
- Navigation becomes a 3-column touch grid.
- Auth buttons become touch-sized.
- Main layout stacks vertically instead of using fixed desktop columns.
- Map appears first and keeps a large usable height.
- Filter/sidebar appears below the map at full width.
- Right detail panel appears below filters at full width.
- Timeline becomes sticky at the bottom.
- Period buttons, checkboxes, and tabs get larger touch targets.
- Forecast period cells wrap into 3 columns on tablet and 2 columns on small phones.
- Auth modal is constrained to fit inside small screens.

## Browser QA

Local QA URL:

```text
http://127.0.0.1:8765/index.html?qa=responsive
```

Desktop viewport:

- 1280 x 720
- No console errors.
- Desktop layout kept the existing left/map/right structure.

Mobile viewport:

- 390 x 844 override.
- No horizontal overflow.
- Left panel width: 375px.
- Right panel width: 375px.
- Map height: about 439px.
- Navigation button height: 42px.
- Period button height: 42px.
- No console errors.
- Login modal opened and fit within the viewport.
- 4-week period button remained clickable.

QA screenshot:

- `docs/session_91_mobile_qa_screenshot.png`

## Automated Validation

Commands run locally:

```powershell
git diff --check
python scripts\run_smoke_suite.py --timeout-seconds 300
$env:PYTHONPATH='backend'; python -m pytest backend\tests\test_api.py backend\tests\test_horizon_forecasts.py -q
```

Results:

- whitespace check passed
- smoke suite passed
- backend API and horizon tests passed: 39 passed, 1 warning

## Next Beta QA Step

Continue with:

- real production deployment check after CI
- mobile production smoke at `https://mk-map.com`
- layer combinations: FarmMap + market + weather
- item switching on mobile
- right detail panel content density for elderly users
