# AI Session 119 - Customs Trade Stability Pass

Date: 2026-07-07

## Goal

Improve the stability of customs import/export integration. The previous direct model-training candidate connected customs data, but rolling backtests regressed. The goal of this pass was to keep customs data useful while preventing it from destabilizing the price model.

## What Changed

### 1. Crop-Specific Customs Features

The training table no longer exposes generic customs fields such as `customs_import_weight_log`.

Instead, customs features are item-gated:

- `customs_cabbage_import_weight_log`
- `customs_onion_import_yoy_change`
- `customs_garlic_import_3m_pressure`
- and so on

Validation result:

- `cross_item_leaks`: 0
- This means onion customs values do not appear in cabbage rows, garlic rows, etc.

### 2. Smaller Feature Set

The customs feature set was reduced from 10 metrics per crop to 4 metrics per crop:

- `import_weight_log`
- `import_mom_change`
- `import_yoy_change`
- `import_3m_pressure`

This reduced the customs columns from 160 to 64 and cuts down overfitting risk.

### 3. Conservative Item Matching

The collector now filters mixed HS rows more strictly:

- `carrot` keeps only `statKor == 당근`, excluding `순무`.
- `tomato` keeps only `방울토마토`, excluding vague `기타`.
- `radish`, `fresh_pepper`, `perilla`, and `chamoe` remain inactive for customs features until exact mapping is verified.

### 4. Customs Month Fallback

Customs data is monthly and often published later than price data. The training builder now uses the latest available customs month on or before the previous month.

Example:

- Price row date: 2026-07-03
- Previous month: 2026-06
- Latest available customs month: 2026-05
- The engine uses 2026-05 customs data instead of producing all-zero features.

### 5. Safe Prediction Overlay

Directly retraining the model with customs features still did not pass rolling-backtest stability. So production predictions keep the stable checked model and apply a bounded customs overlay at prediction time.

The overlay is used only for horizons of 30 days or longer.

Formula:

```text
import_pressure =
  0.5 * import_3m_pressure
  + 0.3 * import_yoy_change
  + 0.2 * import_mom_change

customs_adjustment = -import_pressure * horizon_scale
```

Interpretation:

- Import pressure positive means imports are rising, so domestic price gets a small downward adjustment.
- Import pressure negative means imports are falling, so domestic price gets a small upward adjustment.

Horizon scales:

- 30d: 0.012
- 90d: 0.018
- 180d: 0.024

## Verification

Generated:

- `data/model/price_training_table_20260706.csv`
- `data/model/latest_price_horizon_predictions_20260706_customs_overlay_check.json`
- `data/model/horizons/price_horizon_model_20260706_customs_item_gated_compact_comparison.json`

Latest-row feature checks:

- Cabbage: customs import pressure is negative, so the overlay nudges the forecast upward.
- Carrot: customs import pressure is positive, so the overlay nudges the forecast downward.
- Radish: no customs features attached because current mapping is not safe.

Nonzero overlay count:

- 27 item-horizon combinations across 30d, 90d, and 180d.

Sample overlay effects:

| Item | Horizon | Adjustment | Meaning |
| --- | ---: | ---: | --- |
| cabbage | 30d | +0.123%p | Imports softened, small upside pressure. |
| carrot | 30d | -0.120%p | Import pressure present, small downside pressure. |
| garlic | 180d | -0.299%p | Import pressure present, medium-term downside pressure. |
| potato | 180d | +0.393%p | Imports softened, medium-term upside pressure. |
| sweet_potato | 180d | +0.454%p | Imports softened, medium-term upside pressure. |

## Model Decision

Do not promote the directly retrained customs-feature model yet.

Use the current stable checked model plus the bounded customs overlay. This is safer because:

- Rolling backtest remains anchored to the existing stable model.
- Customs data changes the displayed forecast only within a small bounded range.
- The adjustment is visible in output as `customs_trade_overlay`, so UI/explanation layers can tell users why the rate moved.

## Answer To The Matching Question

Yes, the intended behavior is that customs data only affects the same crop engine.

Current implementation enforces this in two ways:

1. The training table uses columns prefixed with the item code, for example `customs_onion_*`.
2. A validation check confirmed there are no cross-item nonzero customs features.

Rows with unsafe HS/statKor mapping are not attached to the crop engine.
