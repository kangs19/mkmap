# Session 100 - Dashboard Statistics Panel

Date: 2026-07-06

## Goal

Turn the top `통계` navigation view into a useful decision dashboard instead of a thin statistics page.

## Changed Files

- `index.html`

## What Changed

- Expanded `renderDashboardPanel`.
- Added a new "오늘 우선순위" judgment at the top.
- Added compact status pills for:
  - price data count,
  - caution item count,
  - forecast-ready item count,
  - shipment metadata count.
- Added or improved rank sections:
  - 오늘 우선 확인,
  - 상승 압력 순위,
  - 하락 압력 순위,
  - 가격 이상치 순위,
  - 위험 점수 순위,
  - 상승·하락 확률 신호,
  - 출하 규모 순위,
  - 산지 집중도 순위,
  - 예측 데이터 준비 순위.
- Added derived metrics per crop:
  - representative shipment total,
  - top production/shipment region,
  - production concentration,
  - max regional price gap,
  - 4-week and 3-month model change,
  - priority score.
- Data-empty handling was hardened:
  - rows without any price, production, forecast, or live signal data are not forced into rankings.
  - empty sections show `아직 비교 가능한 데이터가 없습니다.`
  - the top judgment says data is being collected instead of showing misleading `0점`.
- Fixed awkward particle output such as `배추은` by using `topicName`.

## Verification

- `git diff --check` passed.
- `python scripts\run_smoke_suite.py --timeout-seconds 300` passed.
- Browser local check:
  - `통계` panel opened,
  - new sections appeared,
  - no misleading `우선점수 0점입니다`,
  - no `배추은`,
  - no-data fallback text appeared correctly.

## Follow-Up

- After production deploy, manually check the dashboard with live data loaded:
  - priority ranking should not be empty once API caches are available,
  - clicking a rank row should switch back to map mode with the selected crop,
  - mobile layout should remain readable because the dashboard can now contain many rank cards.
- Next useful QA slice:
  - weather layer visibility and weather icons,
  - map layer toggle meaning,
  - mobile detail-panel readability.
