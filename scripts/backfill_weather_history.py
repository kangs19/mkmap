"""KMA 작물별 날씨 과거 데이터 백필.

collect_live_weather_features.py를 날짜 루프로 호출해
지정 기간의 날씨 데이터를 일괄 수집한다.
이미 존재하는 날짜는 --force 없이는 스킵.

Usage:
    python scripts/backfill_weather_history.py --start 2025-05-04
    python scripts/backfill_weather_history.py --start 2025-05-04 --end 2026-06-30
    python scripts/backfill_weather_history.py --start 2025-05-04 --force  # 덮어쓰기
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = REPO_ROOT / "data" / "features"


def has_weather_data(target_date: date, items: list[str]) -> bool:
    stamp = target_date.strftime("%Y%m%d")
    folder = FEATURES_DIR / stamp
    if not folder.exists():
        return False
    for item in items:
        f = folder / f"kma_crop_weather_{item}.json"
        if not f.exists():
            return False
        # 파일이 비어있거나 빈 배열이면 재수집
        try:
            import json
            data = json.loads(f.read_text(encoding="utf-8"))
            if not data:
                return False
        except Exception:
            return False
    return True


def collect_one_day(target_date: date, items: list[str], timeout: int = 25) -> bool:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "collect_live_weather_features.py"),
        "--date", target_date.isoformat(),
        "--items", *items,
        "--max-requests-per-item", "0",
        "--request-timeout-seconds", "10",
    ]
    try:
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), timeout=timeout, capture_output=True, text=True)
        ok = result.returncode == 0
        if not ok:
            print(f"  [WARN] exit={result.returncode} stderr={result.stderr[-200:]}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"  [WARN] timeout after {timeout}s")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="시작일 YYYY-MM-DD")
    p.add_argument("--end", default=date.today().isoformat(), help="종료일 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--items", nargs="*",
                   default=["cabbage", "radish", "onion", "green_onion", "garlic"],
                   help="수집할 품목 목록")
    p.add_argument("--force", action="store_true", help="이미 있는 날짜도 덮어쓰기")
    p.add_argument("--sleep", type=float, default=0.5,
                   help="요청 간 대기 시간(초). API 과부하 방지 (기본: 0.5)")
    p.add_argument("--timeout", type=int, default=25,
                   help="날짜별 수집 subprocess 타임아웃(초) (기본: 25)")
    p.add_argument("--dry-run", action="store_true", help="실제 수집 없이 수집 대상 날짜만 출력")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    items = args.items

    # 수집 대상 날짜 목록
    all_dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    if not args.force:
        pending = [d for d in all_dates if not has_weather_data(d, items)]
    else:
        pending = all_dates

    print(f"전체 {len(all_dates)}일, 수집 필요 {len(pending)}일 (스킵 {len(all_dates)-len(pending)}일)")
    print(f"기간: {start} ~ {end}, 품목: {items}")

    if args.dry_run:
        for d in pending[:20]:
            print(f"  {d}")
        if len(pending) > 20:
            print(f"  ... 외 {len(pending)-20}일")
        return 0

    ok_count = 0
    fail_count = 0
    for idx, d in enumerate(pending, 1):
        print(f"[{idx}/{len(pending)}] {d} ", end="", flush=True)
        ok = collect_one_day(d, items, timeout=args.timeout)
        if ok:
            print("OK")
            ok_count += 1
        else:
            print("FAIL")
            fail_count += 1
        if idx < len(pending):
            time.sleep(args.sleep)

    print(f"\n완료: OK={ok_count} FAIL={fail_count} / {len(pending)}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
