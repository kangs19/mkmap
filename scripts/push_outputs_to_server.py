"""Push locally-generated signal/forecast outputs to a running backend server.

Usage:
    python scripts/push_outputs_to_server.py \
        --date 2026-07-01 \
        --server https://mk-map.com \
        --admin-key <ADMIN_KEY>

This bypasses the need for API keys on the Railway server: run the pipeline
locally with real API keys, then push the results to Railway's DB via this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.env import ensure_env_loaded
from mkmap_meta.storage import data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push pipeline outputs to a backend server via admin API.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--server", default="https://mk-map.com")
    parser.add_argument("--admin-key", default=None, help="ADMIN_KEY (or set ADMIN_KEY env var)")
    parser.add_argument("--signals-only", action="store_true")
    parser.add_argument("--predictions-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_env_loaded()
    admin_key = args.admin_key or os.getenv("ADMIN_KEY", "")
    if not admin_key:
        print("[ERROR] ADMIN_KEY is required (--admin-key or ADMIN_KEY env var)", file=sys.stderr)
        return 1

    target_date = date.fromisoformat(args.date)
    stamp = f"{target_date:%Y%m%d}"
    signals_path = data_dir() / "signals" / stamp / "region_risk_signals.json"
    predictions_path = data_dir() / "model" / f"latest_price_predictions_{stamp}_risk.json"

    body: dict = {}

    if not args.predictions_only:
        if not signals_path.exists():
            print(f"[ERROR] Signals file not found: {signals_path}", file=sys.stderr)
            return 1
        body["signals"] = json.loads(signals_path.read_text(encoding="utf-8"))
        print(f"[INFO] Loaded signals: {len(body['signals'])} items from {signals_path.relative_to(REPO_ROOT)}")

    if not args.signals_only:
        if not predictions_path.exists():
            print(f"[WARN] Predictions file not found, skipping: {predictions_path}", file=sys.stderr)
        else:
            body["predictions"] = json.loads(predictions_path.read_text(encoding="utf-8"))
            print(f"[INFO] Loaded predictions: {len(body['predictions'])} items from {predictions_path.relative_to(REPO_ROOT)}")

    if not body:
        print("[ERROR] Nothing to push", file=sys.stderr)
        return 1

    url = f"{args.server.rstrip('/')}/api/v1/admin/import-outputs?target_date={args.date}"
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Key": admin_key,
        },
        method="POST",
    )
    print(f"[INFO] POSTing to {url} ({len(payload)} bytes)...")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"\n[OK] signals_imported={result.get('signals_imported',0)}  forecasts_imported={result.get('forecasts_imported',0)}")
        return 0
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"[ERROR] HTTP {exc.code}: {body_text}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
