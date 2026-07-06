# AI Session 106 - Default Panel Readability

Date: 2026-07-06

## Goal

Improve the right-side default panel shown before a map region is selected. The user said the app should be usable by older farmers and should show judgment, not feature explanations or tiny labels.

## Changed

- Added reusable default-panel text styles:
  - `.fm-brief-card`
  - `.fm-brief-title`
  - `.fm-brief-note`
  - `.fm-brief-value`
  - `.fm-brief-small`
  - `.fm-brief-pill`
- Increased the right default panel summary from 12px to 14px.
- Increased section labels from 9px uppercase-style labels to readable 12px Korean labels.
- Changed default map guide copy to a short action-oriented judgment:
  - "색이 진한 지역부터 확인하세요."
  - "클릭하면 가격·재배·시장 판단이 열립니다."
- Reworked "오늘 볼 체크포인트" cards:
  - larger item names and values;
  - clearer action judgment such as checking rising pressure, falling pressure, or stable outliers;
  - region notes now say which region to check first.
- Reworked "기준 시세" cards:
  - larger price values;
  - simpler direction labels such as 상승 쪽 확인, 하락 쪽 확인, 보합권.
- Reworked data-status rows with larger labels, values, and notes.

## Validation

- `git diff --check` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.

## Next Work

- Continue UI readability cleanup inside selected-region detail tabs, especially dense risk/trend text.
- If doing visual QA, use a normal browser or a fresh Codex browser tab because old in-app browser site data may still show a stale WordPress redirect error.
