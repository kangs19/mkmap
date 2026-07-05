# AI Session 73 - Risk Readability And Senior-Friendly Detail Panel

Date: `2026-07-05`

## User Feedback

The right-side price detail panel was too small and too explanatory. The user wants the panel to tell an older farmer or market user what the measured score means now, not just what the feature does.

Specific feedback:

- Risk rows should interpret the current score per category.
- The total risk score needs an overall judgment.
- Tiny text in the price and risk areas is hard to read for older users.
- Source-style copy such as "agromarket wholesale transaction data..." should not be shown as primary UI copy.
- The UI should focus on judgment: what the data implies and what the user should watch next.

## Change Made

- Increased right-panel readability:
  - region name/subtitle,
  - price labels and badges,
  - market basis copy,
  - horizon mini forecast labels,
  - risk title, summary, row text, and source notes.
- Added risk judgment rendering:
  - `riskJudgment(key, score, ctx)` produces category-specific status copy.
  - `riskOverallComment(risk)` produces the total-score summary.
  - `riskBarsHtml(..., showBasis:true)` now displays a readable judgment card below each risk bar.
- Replaced visible source-copy in the price panel and hover card with `priceBasisJudgment(...)`, which explains whether the current market price looks high, low, stable, or directionally pressured.
- Kept existing data calculations intact. This pass changed how scores are explained to users, not the score formula itself.

## Important Design Direction

For this product, avoid copy that says only "this is calculated from X data." Users need operational interpretation:

- Bad: "The score is based on weather, production, and market data."
- Good: "Weather pressure is low, so current price movement is more likely coming from market price and shipment flow."

For older users, detail-panel microcopy should generally be at least `12px`, with key labels closer to `13-14px`. Do not shrink important judgment text just to make the panel look denser.

## Files Changed

- `index.html`

## Verification

- `python scripts\check_text_encoding_health.py`: passed.
- `python -m pytest tests\test_api.py -q`: passed, `33 passed`.
- `python scripts\run_smoke_suite.py --timeout-seconds 300`: passed.
- Browser check on `http://127.0.0.1:8027/index.html`:
  - page loads,
  - right-panel font sizes are applied,
  - old visible source phrase is not present in body text,
  - no new script error was observed.

## Follow-Up

- The current detail panel still needs a direct interaction verification after a map-region click in a full app session with backend data attached.
- The risk score formula itself may need a later product pass. This session focused on explaining existing measured scores more clearly.
- Future Korean copy should ideally move out of large inline template strings into a UTF-8-safe dictionary or JSON data block.
