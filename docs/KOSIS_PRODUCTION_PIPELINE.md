# KOSIS Production Pipeline

This pipeline collects crop production and cultivation-area features from KOSIS and converts them into region-level production weights.

## Source Tables

- `cabbage`: `DT_1ET0028`, crop production survey, leafy vegetables
- `radish`: `DT_1ET0029`, crop production survey, root vegetables
- `onion`: `DT_1ET0291`, crop production survey, spice and culinary vegetables
- `green_onion`: `DT_1ET0291`, crop production survey, spice and culinary vegetables
- `garlic`: `DT_1ET0291`, crop production survey, spice and culinary vegetables

The connector reads KOSIS rows where `ITM_NM` contains the mapped item name and ends with `:면적` or `:생산량`, excluding `10a당 생산량`. This is necessary because cabbage and radish often publish usable values under seasonal sub-items such as `노지가을배추`.

## Commands

```powershell
python scripts\test_live_kosis_production.py --item cabbage --year 2026
python scripts\collect_live_production_features.py --date 2026-06-30 --year 2026
python scripts\build_model_dataset.py --date 2026-06-30
python scripts\export_live_signals.py --date 2026-06-30
```

## Current Run

- `2026-06-30` collection succeeded for all 5 items.
- Cabbage, radish, onion, and garlic used KOSIS year `2025`.
- Green onion used KOSIS year `2024`.
- Each item produced 17 province-level features.
- Region-risk dataset grew from the manual 15 rows to 85 KOSIS-backed rows.

## Notes

- `.env` may still contain an old `KOSIS_PRODUCTION_ITEM_PARAM=item_code`; the connector normalizes this to KOSIS official `itmId`.
- Generated feature files under `data/features/` are ignored by Git.
