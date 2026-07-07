# AI Session 117 - Customs Trade Feature Audit

Date: 2026-07-07

## Goal

Download the newly approved customs import/export API data and decide which rows can be connected to the MK-MAP crop price prediction engine.

## What Was Verified

Two Korea Customs Service public-data endpoints were live-tested with the configured public-data API key. The key is intentionally not stored in this document.

- National item trade: `http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList`
- Item-by-country trade: `http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList`

The audit script requests the latest one-year window allowed by the service and summarizes rows by crop candidate, HS prefix, import weight, import value, export weight, export value, and top origin countries.

## Files Added

- `scripts/audit_customs_trade_features.py`
  - Re-runnable live API audit script.
  - Loads `.env`, but does not print API keys.
  - Writes summarized output under `data/audits/customs_trade/`.

- `config/customs_trade_hs_candidates.json`
  - Engine-facing mapping candidate file.
  - Separates high-confidence mappings from HS prefixes that need item-name review.

- `data/audits/customs_trade/customs_trade_feature_audit_202507_202606.json`
  - Latest generated audit output.
  - This is data output, not a secret. It contains summarized public API results only.

## Audit Summary

Window tested: 2025-07 to 2026-06 request window. The API returned actual monthly rows mainly through 2026-05, which is expected for customs monthly statistics.

- Tested crops: 22
- Tested HS prefixes: 24
- Ready for import-pressure feature: 11
- Usable after HS/statKor review: 9
- Reference only because HS bucket is too broad: 2
- No recent import weight: 2
- API errors: 0

## Strongest Engine Candidates

These can be connected first as `import_export_pressure` features.

| Crop | HS Prefix | Why It Matters |
| --- | --- | --- |
| Onion | `070310` | Very large recent import volume, mostly China. Strong medium-term price pressure candidate. |
| Carrot | `070610` | Very large import volume. Useful for judging whether domestic prices can be capped by imports. |
| Sesame | `120740` | Very large import volume and clear HS mapping. |
| Potato | `070190` | Large import volume from the US/Australia. Useful substitution pressure feature. |
| Grape | `080610` | Strong seasonal import flow from Australia/Chile/Peru. |
| Garlic | `070320` | Clear garlic import rows, mostly China. |
| Sweet potato | `071420` | Smaller but usable import data. |
| Spinach | `070970` | Low volume, but clear enough for spike detection. |
| Tomato | `070200` | Clear mapping, but current volume is near zero. Use as a low-pressure or spike feature. |
| Apple | `080810` | Near-zero imports. Good as a no-import baseline/spike detector. |
| Strawberry | `081010` | Near-zero imports. Good as a no-import baseline/spike detector. |

## Needs Review Before Training

These have useful data, but the HS prefix contains similar or mixed items. Before training, filter by `statKor` or split variants.

- Cabbage / 배추: `070490`
- Radish / 무: `070690`
- Green onion / 대파: `070390`
- Dried pepper / 건고추: `090421`, `090422`
- Fresh pepper / 풋고추: `070960`
- Cucumber / 오이: `070700`
- Lettuce / 상추: `070511`, `070519`

## Do Not Train Directly Yet

- Chamoe / 참외: `080719`
  - The HS prefix is a melon-family bucket. Needs exact item-name filtering.
- Perilla leaf / 깻잎: `070999`
  - The HS prefix is a broad “other vegetables” bucket. Current rows include several unrelated vegetables.

## No-Recent-Import Baseline

- Watermelon / 수박: `080711`
- Pear / 배: `080830`

Rows exist, but the tested window had no import weight. These should not add price pressure, but they are still useful as a baseline showing that imports are not currently a driver.

## Recommended Engine Features

Add a trade/import feature family to the crop engine:

- `import_weight_1m_kg`
- `import_weight_3m_avg_kg`
- `import_weight_yoy_pct`
- `import_weight_mom_pct`
- `import_unit_value_usd_per_kg`
- `dominant_origin_country`
- `origin_concentration_pct`
- `export_weight_1m_kg`
- `import_pressure_score`

Because customs data is monthly, it should mainly influence 4-week, 2-month, and 3-month predictions. It should not dominate 1-week predictions unless the item has a very abrupt import spike.

## Next Implementation Steps

1. Add a `TradeFeature` or `ImportExportFeature` model in `mkmap_meta/models.py`.
2. Add a `CustomsTradeConnector` that reads `config/customs_trade_hs_candidates.json`.
3. Normalize rows into monthly item features.
4. Join the monthly features into the training table with month-end carry-forward logic.
5. Backtest with and without trade features by crop and horizon.
6. Promote the feature only where it improves validation or explanation quality.

## Cautions

- Do not print `.env` or API keys in logs.
- Do not train broad HS prefixes directly without `statKor` filtering.
- Do not use marine/fishery import APIs for the current crop engine unless MK-MAP expands to fishery items.
- City/province customs APIs are approved but their exact operation path has not been verified yet. Use the national and country endpoints first, then add regional trade APIs after endpoint confirmation.
