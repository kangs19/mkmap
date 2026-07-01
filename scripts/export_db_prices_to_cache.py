"""Export daily_prices rows from backend PostgreSQL into kamis_price feature cache files.

Runs before build_price_training_table.py so that CachedPriceConnector finds
historical price data even when the /app/data/features/ directory is empty
(e.g. on Railway where the container filesystem is ephemeral).

Soft-exits (code 0) if DATABASE_URL is not PostgreSQL, so local SQLite
environments are unaffected.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export DB prices to feature cache JSON files.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Target date YYYY-MM-DD (cache folder)")
    parser.add_argument("--days-back", type=int, default=90, help="Days of price history to export")
    return parser.parse_args()


def _resolve_asyncpg_url(raw: str) -> str | None:
    """Return asyncpg-compatible URL, or None if not PostgreSQL."""
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql://", 1)
    if raw.startswith("postgresql://") and "+asyncpg" not in raw and "+psycopg" not in raw:
        return raw
    if raw.startswith("postgresql+asyncpg://"):
        return raw.replace("postgresql+asyncpg://", "postgresql://", 1)
    return None


async def main_async() -> int:
    args = parse_args()
    target_date = date.fromisoformat(args.date)
    start_date = target_date - timedelta(days=args.days_back)

    raw_url = os.environ.get("DATABASE_URL", "")
    pg_url = _resolve_asyncpg_url(raw_url)
    if not pg_url:
        print(f"[export_db_prices] DATABASE_URL is not PostgreSQL ({raw_url[:30]!r}…), skipping.", file=sys.stderr)
        return 0

    try:
        import asyncpg
    except ImportError:
        print("[export_db_prices] asyncpg not installed, skipping.", file=sys.stderr)
        return 0

    try:
        conn = await asyncpg.connect(pg_url, timeout=15)
    except Exception as exc:
        print(f"[export_db_prices] DB connect failed: {exc}", file=sys.stderr)
        return 0

    try:
        rows = await conn.fetch(
            """
            SELECT item_code, date, wholesale_price, retail_price, source
            FROM daily_prices
            WHERE date >= $1 AND date <= $2 AND source = 'kamis'
            ORDER BY item_code, date
            """,
            start_date,
            target_date,
        )
    except Exception as exc:
        print(f"[export_db_prices] DB query failed: {exc}", file=sys.stderr)
        await conn.close()
        return 0
    finally:
        await conn.close()

    # Group by item_code
    by_item: dict[str, list[dict]] = {}
    for row in rows:
        item_code = row["item_code"]
        by_item.setdefault(item_code, []).append(
            {
                "item_code": item_code,
                "region_code": None,
                "base_date": row["date"].isoformat(),
                "retail_price": row["retail_price"],
                "wholesale_price": row["wholesale_price"],
                "settlement_price": None,
                "volume": None,
                "source": row["source"] or "kamis",
                "raw": {},
            }
        )

    stamp = f"{target_date:%Y%m%d}"
    features_dir = REPO_ROOT / "data" / "features" / stamp
    features_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for item_code, features in by_item.items():
        out_path = features_dir / f"kamis_price_{item_code}.json"
        # Merge with existing cache (don't overwrite fresher data)
        existing: list[dict] = []
        if out_path.exists():
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing_dates = {r["base_date"] for r in existing if isinstance(r, dict)}
        merged = existing + [f for f in features if f["base_date"] not in existing_dates]
        merged.sort(key=lambda r: r["base_date"])
        out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        written += len(merged)
        print(f"  {item_code}: {len(merged)} rows → {out_path.relative_to(REPO_ROOT)}")

    print(f"[export_db_prices] Wrote {len(by_item)} item files, {written} total rows")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
