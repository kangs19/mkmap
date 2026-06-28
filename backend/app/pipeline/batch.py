"""
전 품목 일괄 파이프라인 실행기
가격예측 + RegionSignal 모두 실행
"""
import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.database import AsyncSessionLocal
from app.models.item import Item
from sqlalchemy import select

# 품목별 대표 날씨 지역 (가장 핵심 산지)
PRIMARY_WEATHER_REGION = {
    "cabbage":     "KR-42",  # 강원 (여름 고랭지)
    "radish":      "KR-42",  # 강원 (여름 고랭지)
    "onion":       "KR-46",  # 전남 (무안)
    "green_onion": "KR-46",  # 전남 (진도)
    "garlic":      "KR-47",  # 경북 (의성)
}


async def run_batch(base_date: date = None, verbose: bool = True):
    if base_date is None:
        base_date = date.today()

    if verbose:
        print(f"\n{'='*50}")
        print(f"  전 품목 파이프라인 실행: {base_date}")
        print(f"{'='*50}")

    # 활성 품목 목록
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Item).where(Item.is_active == True))
        items = r.scalars().all()

    results = {}

    # ── 1. 가격 예측 파이프라인 ───────────────────────────────
    from app.pipeline.runner import run_pipeline
    if verbose:
        print("\n[1단계] 가격 예측 파이프라인")

    for item in items:
        item_code = item.item_code
        weather_region = PRIMARY_WEATHER_REGION.get(item_code, "KR-42")

        # runner.py의 PRIMARY_WEATHER_REGION을 임시 패치
        import app.pipeline.runner as runner_mod
        runner_mod.PRIMARY_WEATHER_REGION = weather_region

        try:
            r = await run_pipeline(item_code=item_code, base_date=base_date, verbose=False)
            results[item_code] = {"forecast": r, "status": "ok"}
            if verbose:
                dir_sym = "↑" if r["direction"] == "up" else ("↓" if r["direction"] == "down" else "→")
                print(f"  {item.item_name:6s} {dir_sym} {r['up_probability']:.0%} "
                      f"| AUC {r['dir_auc']:.3f} | {r['confidence']}")
        except Exception as e:
            results[item_code] = {"status": "error", "error": str(e)}
            if verbose:
                print(f"  {item.item_name:6s} 오류: {e}")

    # ── 2. 지역 위험 신호 계산 ───────────────────────────────
    from app.pipeline.signals import compute_region_signals
    if verbose:
        print("\n[2단계] 지역 위험 신호 계산")

    for item in items:
        try:
            sigs = await compute_region_signals(item.item_code, base_date, verbose=False)
            results[item.item_code]["signals"] = sigs
            if verbose:
                high = [s for s in sigs if s["risk_level"] in ("warning", "high")]
                status = f"핫스팟 {len(high)}개" if high else "정상"
                print(f"  {item.item_name:6s} 지역 {len(sigs)}개 | {status}")
        except Exception as e:
            if verbose:
                print(f"  {item.item_name:6s} 신호 오류: {e}")

    if verbose:
        print(f"\n완료! {len(items)}개 품목 처리")

    return results


if __name__ == "__main__":
    asyncio.run(run_batch())
