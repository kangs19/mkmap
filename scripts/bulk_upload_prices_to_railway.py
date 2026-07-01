"""로컬 KAMIS 가격 캐시 → Railway DB bulk upload.

로컬에 이미 수집된 가격 데이터(CSV/JSON)를 Railway의
POST /admin/import-prices 엔드포인트로 전송.

Usage:
    python scripts/bulk_upload_prices_to_railway.py \
        --input data/model/price_training_table_20260702.csv \
        --railway-url https://mk-map.com \
        --dry-run

    # 또는 KAMIS API에서 직접 수년치 수집 후 업로드:
    python scripts/bulk_upload_prices_to_railway.py \
        --collect-years 3 \
        --railway-url https://mk-map.com

필수 환경변수 (로컬 .env에서 로드):
    ADMIN_KEY          Railway의 ADMIN_KEY와 동일한 값
    RAILWAY_URL        선택적 (--railway-url 로 덮어쓰기 가능)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# .env 로드
def _load_env():
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        # Codex 경로 시도
        alt = Path(r"C:\Users\kang_\Documents\Codex\2026-06-29\kang-s19-naver-com-rkdtn3303-git\.env")
        if alt.exists():
            env_path = alt
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

_load_env()

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    try:
        import urllib.request as _urllib_req
        import urllib.error as _urllib_err
        HAS_URLLIB = True
    except ImportError:
        HAS_URLLIB = False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=None,
                   help="CSV 또는 JSON 파일 경로 (price_training_table_*.csv 등)")
    p.add_argument("--collect-years", type=int, default=0,
                   help="KAMIS API에서 직접 수집할 기간(년). 0이면 --input만 사용")
    p.add_argument("--railway-url", default=os.environ.get("RAILWAY_URL", "https://mk-map.com"))
    p.add_argument("--admin-key", default=os.environ.get("ADMIN_KEY", ""))
    p.add_argument("--chunk-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true", help="전송하지 않고 데이터만 파싱 확인")
    return p.parse_args()


# ── 로컬 CSV 파싱 ──────────────────────────────────────────────────────────────

def load_from_training_csv(path: Path) -> list[dict]:
    """price_training_table CSV에서 raw price rows 재구성."""
    rows = []
    seen: set[tuple] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                item_code = row.get("item_code", "")
                base_date = row.get("base_date", "")
                # avg_price는 정규화된 값, lag_1_price (원본 가격) 없으면 스킵
                lag1 = row.get("lag_1_price")
                if not lag1:
                    continue
                price = float(lag1)  # lag_1 = 1일 전 실제 가격
                if price <= 0:
                    continue
                key = (item_code, base_date)
                if key in seen:
                    continue
                seen.add(key)
                # base_date의 가격은 lag_1이 해당일 가격
                rows.append({
                    "item_code": item_code,
                    "date": base_date,
                    "wholesale_price": round(price, 2),
                    "retail_price": None,
                    "market": "",
                    "grade": "",
                    "source": "kamis",
                })
            except (ValueError, KeyError):
                continue
    return rows


def load_from_json(path: Path) -> list[dict]:
    """JSON 형식 가격 파일 로드."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "prices" in data:
        return data["prices"]
    return []


def load_from_kamis_cache(data_root: Path) -> list[dict]:
    """로컬 KAMIS 캐시 폴더에서 가격 수집."""
    rows = []
    for jf in sorted(data_root.glob("**/*prices*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                rows.extend(data)
        except Exception:
            continue
    return rows


# ── HTTP 전송 ──────────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, admin_key: str, timeout: int = 60) -> dict:
    headers = {"Content-Type": "application/json", "X-Admin-Key": admin_key}
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    if HAS_HTTPX:
        with httpx.Client(timeout=timeout, verify=False) as client:
            resp = client.post(url, content=body_bytes, headers=headers)
            resp.raise_for_status()
            return resp.json()
    else:
        req = _urllib_req.Request(url, data=body_bytes, headers=headers, method="POST")
        with _urllib_req.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())


def upload_chunk(
    rows: list[dict],
    railway_url: str,
    admin_key: str,
    chunk_size: int = 500,
    dry_run: bool = False,
) -> dict:
    url = railway_url.rstrip("/") + "/admin/import-prices"
    total_saved = 0
    total_skipped = 0

    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        if dry_run:
            print(f"  [dry-run] chunk {i//chunk_size}: {len(chunk)} rows (no request sent)")
            continue
        try:
            result = _post_json(url, {"prices": chunk}, admin_key)
            saved = result.get("saved", 0)
            skipped = result.get("skipped", 0)
            total_saved += saved
            total_skipped += skipped
            print(f"  chunk {i//chunk_size}: sent={len(chunk)} saved={saved} skipped={skipped}")
            time.sleep(0.3)  # 서버 과부하 방지
        except Exception as e:
            print(f"  [ERROR] chunk {i//chunk_size} failed: {e}", file=sys.stderr)
            time.sleep(2)

    return {"total_saved": total_saved, "total_skipped": total_skipped}


# ── KAMIS API 직접 수집 ────────────────────────────────────────────────────────

async def collect_from_kamis(years: int) -> list[dict]:
    """KAMIS periodProductList로 수년치 직접 수집."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        from app.collectors.kamis import fetch_period_prices, ITEM_CODE_MAP
    except ImportError:
        print("[ERROR] FastAPI 앱을 import할 수 없음. REPO_ROOT/backend가 필요합니다.", file=sys.stderr)
        return []

    import asyncio
    from datetime import date, timedelta

    end_date = date.today()
    start_date = end_date - timedelta(days=365 * years)
    all_rows = []

    for item_code in ITEM_CODE_MAP:
        print(f"  Collecting {item_code} from {start_date} to {end_date}...")
        try:
            rows = await fetch_period_prices(item_code, start_date, end_date)
            all_rows.extend([
                {
                    "item_code": r["item_code"],
                    "date": str(r["date"]),
                    "wholesale_price": r["wholesale_price"],
                    "retail_price": r.get("retail_price"),
                    "market": r.get("market", ""),
                    "grade": r.get("grade", ""),
                    "source": "kamis",
                }
                for r in rows if r.get("wholesale_price", 0) > 0
            ])
            print(f"    → {len(rows)} rows collected")
            asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))
        except Exception as e:
            print(f"    [WARN] {item_code}: {e}")

    return all_rows


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    if not args.admin_key:
        print("[ERROR] ADMIN_KEY가 설정되지 않음. .env 파일 또는 --admin-key 인자를 확인하세요.", file=sys.stderr)
        return 1

    rows: list[dict] = []

    # 1. --input 파일에서 로드
    if args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"[ERROR] 파일 없음: {path}", file=sys.stderr)
            return 1
        print(f"[upload] Loading from {path}")
        if path.suffix == ".csv":
            rows = load_from_training_csv(path)
        else:
            rows = load_from_json(path)
        print(f"[upload] Loaded {len(rows)} rows from local file")

    # 2. KAMIS API에서 직접 수집
    if args.collect_years > 0:
        print(f"[upload] Collecting {args.collect_years} years from KAMIS API...")
        import asyncio
        kamis_rows = asyncio.run(collect_from_kamis(args.collect_years))
        print(f"[upload] Collected {len(kamis_rows)} rows from KAMIS")
        rows.extend(kamis_rows)

    # 중복 제거
    seen: set[tuple] = set()
    deduped = []
    for r in rows:
        key = (r["item_code"], r["date"], r.get("source", "kamis"))
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    print(f"[upload] After dedup: {len(deduped)} rows")

    if not deduped:
        print("[upload] No data to upload.")
        return 0

    # 날짜 범위 확인
    dates = sorted(r["date"] for r in deduped)
    items = list({r["item_code"] for r in deduped})
    print(f"[upload] Items: {items}")
    print(f"[upload] Date range: {dates[0]} ~ {dates[-1]}")

    if args.dry_run:
        print("[upload] DRY RUN - no data will be sent")
        per_item = {}
        for r in deduped:
            per_item.setdefault(r["item_code"], 0)
            per_item[r["item_code"]] += 1
        for item, cnt in sorted(per_item.items()):
            print(f"  {item}: {cnt} rows")
        return 0

    # 전송
    print(f"\n[upload] Uploading to {args.railway_url}/admin/import-prices")
    result = upload_chunk(deduped, args.railway_url, args.admin_key, args.chunk_size)
    print(f"\n[upload] Done: saved={result['total_saved']} skipped={result['total_skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
