from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


FEATURE_LABELS = {
    "price_pct_of_hist_mean": "현재 가격이 과거 평균 대비 어느 위치인지",
    "change_1d": "최근 1일 가격 변화율",
    "change_3d": "최근 3일 가격 변화율",
    "change_7d": "최근 7일 가격 변화율",
    "change_14d": "최근 14일 가격 변화율",
    "ma_7_gap": "현재 가격과 7일 이동평균의 차이",
    "ma_14_gap": "현재 가격과 14일 이동평균의 차이",
    "volatility_7d": "최근 7일 가격 변동성",
    "volatility_14d": "최근 14일 가격 변동성",
    "weekday_sin": "요일 계절성(주간 순환)",
    "weekday_cos": "요일 계절성(주말/평일 축)",
    "month_sin": "월별 계절성(연중 순환)",
    "month_cos": "월별 계절성(상반기/하반기 축)",
    "at_wholesale_norm": "KAMIS 도매 가격 격차",
    "agromarket_wholesale_norm": "AgroMarket 도매 가격 격차",
    "agromarket_retail_norm": "AgroMarket 소매 가격 격차",
    "agromarket_settlement_norm": "공영도매시장 정산 가격 격차",
    "agromarket_volume_norm": "공영도매시장 정산 물량 압력",
    "agromarket_auction_norm": "실시간 경매 가격 격차",
    "agromarket_auction_volume_norm": "실시간 경매 물량 압력",
    "agromarket_auction_dominant_share": "경매 품종 집중도",
    "agromarket_auction_seasonal_share": "계절성 품종 비중",
    "agromarket_auction_stored_share": "저장성 품종 비중",
    "agromarket_auction_processed_share": "가공/손질 품종 비중",
    "agromarket_auction_imported_share": "수입 품종 비중",
    "weather_temp_norm": "주산지 기온 압력",
    "weather_rainfall_norm": "주산지 강수 압력",
    "weather_humidity_norm": "주산지 습도 압력",
    "weather_sunshine_norm": "주산지 일조 압력",
    "weather_obs_norm": "농업기상 관측 강도",
    "supply_rain_reservoir_risk": "지역 강수량/저수율 기반 공급 위험",
    "supply_weather_alert_insurance_risk": "기상특보/재해보험 결합 공급 위험",
    "cabbage_kimjang_urgency_30d": "배추 김장철 30일 임박도",
    "cabbage_kimjang_urgency_90d": "배추 김장철 90일 임박도",
    "cabbage_season_phase": "배추 출하 계절 구간",
    "cabbage_highland_temp_stress": "배추 고랭지 고온 스트레스",
    "cabbage_autumn_supply_pressure": "배추 가을 출하 물량 압력",
    "cabbage_kimjang_vol_spike": "배추 김장철 변동성 확대",
    "radish_kimjang_demand": "무 김장 수요 압력",
    "radish_summer_heat_loss_risk": "무 여름 고온 피해 위험",
    "radish_winter_phase": "무 월동 출하 구간",
    "radish_spring_glut": "무 봄 출하 과잉 위험",
    "onion_storage_depletion_idx": "양파 저장고갈 지수",
    "onion_harvest_proximity_60d": "양파 수확기 60일 임박도",
    "onion_storage_scarcity_risk": "양파 저장 말기 희소성",
    "garlic_storage_month_idx": "마늘 저장 경과 개월 지수",
    "garlic_scarcity_risk": "마늘 저장 말기 희소성",
    "garlic_winter_cold_damage": "마늘 겨울 한파 피해 위험",
    "garlic_harvest_pressure": "마늘 수확기 공급 압력",
    "garlic_post_harvest_down_pressure": "마늘 수확 후 가격 하방 압력",
    "green_onion_heat_stress": "대파 고온 스트레스",
    "green_onion_cold_damage": "대파 한파 피해 위험",
    "green_onion_heavy_rain": "대파 집중강수 압력",
    "green_onion_supply_disruption": "대파 기상 공급차질 지수",
    "green_onion_summer_down_pressure": "대파 여름 하방 압력",
    "green_onion_late_june_normalization": "대파 6월 하순 정상화 압력",
    "radish_summer_glut_pressure": "무 여름 출하 과잉 압력",
    "radish_august_14d_down_pressure": "무 8월 14일 하방 압력",
    "onion_post_harvest_supply_pressure": "양파 수확 후 공급 압력",
    "onion_autumn_storage_transition": "양파 가을 저장 전환 구간",
    "onion_june_rebound_14d": "양파 6월 14일 반등 압력",
    "onion_autumn_14d_correction": "양파 초가을 14일 조정 압력",
    "cabbage_spring_supply_pressure": "배추 봄/초여름 공급 압력",
    "cabbage_may_long_down_pressure": "배추 5월 장기 하방 압력",
    "cabbage_early_autumn_14d_correction": "배추 초가을 14일 조정 압력",
    "garlic_june_post_harvest_softening_14d": "마늘 6월 수확 후 14일 약세 압력",
    "green_onion_august_14d_down_pressure": "대파 8월 14일 하방 압력",
}

ITEM_NAMES = {
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "garlic": "마늘",
    "green_onion": "대파",
}

DIRECTION_LABELS = {
    "up": "상승",
    "down": "하락",
    "stable": "보합",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Explain latest horizon price predictions with linear feature contributions.")
    parser.add_argument("--features", required=True, help="CSV from build_price_training_table.py")
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model-prefix", required=True)
    parser.add_argument("--predictions", required=True, help="Combined horizon prediction JSON")
    parser.add_argument("--quality-report", default=None, help="Optional horizon quality gate JSON")
    parser.add_argument("--output", required=True)
    parser.add_argument("--top-n", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows_by_item = _latest_rows_by_item(Path(args.features))
    predictions = json.loads(Path(args.predictions).read_text(encoding="utf-8"))
    quality_by_horizon = _load_quality(Path(args.quality_report)) if args.quality_report else {}
    models_dir = Path(args.models_dir)

    explained_items = []
    for item in predictions.get("items", []):
        if not isinstance(item, dict):
            continue
        item_code = str(item.get("item_code", ""))
        latest_row = rows_by_item.get(item_code)
        if latest_row is None:
            continue
        explained_horizons: dict[str, Any] = {}
        horizons = item.get("horizons", {})
        if not isinstance(horizons, dict):
            continue
        for horizon_key, prediction in sorted(horizons.items(), key=lambda pair: int(pair[0])):
            if not isinstance(prediction, dict):
                continue
            horizon = int(horizon_key)
            model_path = models_dir / f"{args.model_prefix}_{horizon}d.json"
            if not model_path.exists():
                continue
            model = json.loads(model_path.read_text(encoding="utf-8"))
            active_model, model_scope = _select_model(model, item_code)
            explanation = _explain_prediction(
                item=item,
                prediction=prediction,
                row=latest_row,
                model=active_model,
                model_scope=model_scope,
                quality=quality_by_horizon.get(horizon, {}),
                top_n=args.top_n,
            )
            explained_horizons[horizon_key] = explanation
        explained_items.append(
            {
                "base_date": item.get("base_date"),
                "item_code": item_code,
                "item_name": ITEM_NAMES.get(item_code, item_code),
                "avg_price": item.get("avg_price"),
                "horizons": explained_horizons,
            }
        )

    payload = {
        "ok": True,
        "method": "standardized_linear_feature_contribution",
        "interpretation_note": (
            "각 근거는 선형 예측모델의 표준화 피처 기여도입니다. "
            "가격 등락과 함께 움직인 통계적 근거이며, 단독 인과관계의 확정 증거는 아닙니다."
        ),
        "source_predictions": str(Path(args.predictions)),
        "source_features": str(Path(args.features)),
        "source_quality_report": str(Path(args.quality_report)) if args.quality_report else None,
        "items": explained_items,
        "held_horizons": _held_horizons(predictions, quality_by_horizon),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "items": len(explained_items)}, ensure_ascii=False, indent=2))
    return 0


def _latest_rows_by_item(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            item_code = str(row.get("item_code") or "")
            date = str(row.get("base_date") or row.get("date") or "")
            if not item_code or not date:
                continue
            previous = rows.get(item_code)
            if previous is None or date > str(previous.get("date") or ""):
                rows[item_code] = row
    return rows


def _load_quality(path: Path) -> dict[int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[int, dict[str, Any]] = {}
    for row in payload.get("horizons", []):
        if not isinstance(row, dict):
            continue
        try:
            result[int(row["horizon_days"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return result


def _select_model(model: dict[str, Any], item_code: str) -> tuple[dict[str, Any], str]:
    item_models = model.get("item_models")
    if isinstance(item_models, dict):
        item_model = item_models.get(item_code)
        if isinstance(item_model, dict):
            return item_model, "item"
    return model, "global"


def _explain_prediction(
    *,
    item: dict[str, Any],
    prediction: dict[str, Any],
    row: dict[str, str],
    model: dict[str, Any],
    model_scope: str,
    quality: dict[str, Any],
    top_n: int,
) -> dict[str, Any]:
    predicted_change = _float(prediction.get("risk_adjusted_change", prediction.get("predicted_change")))
    direction = str(prediction.get("risk_adjusted_direction") or prediction.get("predicted_direction") or "stable")
    contributions = _feature_contributions(row, model)
    intercept = _float(model.get("intercept"))
    computed_change = intercept + sum(part["contribution"] for part in contributions)
    supporting, offsetting = _split_contributions(contributions, direction)
    direction_label = DIRECTION_LABELS.get(direction, direction)
    threshold = _float(prediction.get("direction_threshold"))

    summary = _build_summary(direction, predicted_change, threshold, supporting, offsetting)
    return {
        "target_column": prediction.get("target_column"),
        "promotion_status": prediction.get("promotion_status"),
        "hold_reasons": prediction.get("hold_reasons", []),
        "predicted_change": _round(prediction.get("predicted_change")),
        "risk_adjusted_change": _round(predicted_change),
        "predicted_direction": prediction.get("predicted_direction"),
        "risk_adjusted_direction": direction,
        "direction_label": direction_label,
        "direction_threshold": _round(threshold),
        "up_probability": _round(prediction.get("up_probability")),
        "surge_probability": _round(prediction.get("surge_probability")),
        "confidence": prediction.get("confidence"),
        "model_scope": model_scope,
        "quality_gate": _quality_snapshot(quality),
        "computed_change_from_contributions": _round(computed_change),
        "decomposition_delta": _round(predicted_change - computed_change),
        "intercept": _round(intercept),
        "summary": summary,
        "supporting_reasons": [_reason(part, direction, "supporting") for part in supporting[:top_n]],
        "offsetting_reasons": [_reason(part, direction, "offsetting") for part in offsetting[:top_n]],
        "top_absolute_contributions": [
            _reason(part, direction, "absolute")
            for part in sorted(contributions, key=lambda part: abs(part["contribution"]), reverse=True)[:top_n]
        ],
        "basis": {
            "base_date": item.get("base_date"),
            "item_code": item.get("item_code"),
            "item_name": ITEM_NAMES.get(str(item.get("item_code")), str(item.get("item_code"))),
            "avg_price": item.get("avg_price"),
        },
    }


def _feature_contributions(row: dict[str, str], model: dict[str, Any]) -> list[dict[str, Any]]:
    stats = model.get("feature_stats", {})
    coefficients = model.get("coefficients", {})
    result = []
    for feature in model.get("features", []):
        feature_stats = stats.get(feature, {}) if isinstance(stats, dict) else {}
        mean = _float(feature_stats.get("mean"))
        std = _float(feature_stats.get("std"), default=1.0)
        if abs(std) < 1e-12:
            std = 1.0
        raw_value = _float(row.get(feature))
        z_score = (raw_value - mean) / std
        coefficient = _float(coefficients.get(feature)) if isinstance(coefficients, dict) else 0.0
        result.append(
            {
                "feature": feature,
                "label": FEATURE_LABELS.get(feature, feature),
                "raw_value": raw_value,
                "mean": mean,
                "std": std,
                "z_score": z_score,
                "coefficient": coefficient,
                "contribution": coefficient * z_score,
            }
        )
    return result


def _split_contributions(contributions: list[dict[str, Any]], direction: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if direction == "up":
        supporting = [part for part in contributions if part["contribution"] > 0]
        offsetting = [part for part in contributions if part["contribution"] < 0]
    elif direction == "down":
        supporting = [part for part in contributions if part["contribution"] < 0]
        offsetting = [part for part in contributions if part["contribution"] > 0]
    else:
        supporting = sorted(contributions, key=lambda part: abs(part["contribution"]), reverse=True)
        offsetting = []
    supporting.sort(key=lambda part: abs(part["contribution"]), reverse=True)
    offsetting.sort(key=lambda part: abs(part["contribution"]), reverse=True)
    return supporting, offsetting


def _build_summary(
    direction: str,
    predicted_change: float,
    threshold: float,
    supporting: list[dict[str, Any]],
    offsetting: list[dict[str, Any]],
) -> str:
    direction_label = DIRECTION_LABELS.get(direction, direction)
    pct = predicted_change * 100.0
    if direction == "stable":
        main = supporting[0]["label"] if supporting else "주요 피처"
        return f"예측 등락률 {pct:.2f}%는 보합 기준폭 {threshold * 100.0:.2f}% 안에 있습니다. {main} 등 기여가 서로 상쇄된 결과입니다."
    main_reasons = ", ".join(part["label"] for part in supporting[:3]) if supporting else "주요 피처"
    hedge = ""
    if offsetting:
        hedge = f" 반대 방향 요인은 {offsetting[0]['label']}입니다."
    return f"예측 등락률 {pct:.2f}%로 {direction_label} 판단입니다. 주된 근거는 {main_reasons}입니다.{hedge}"


def _reason(part: dict[str, Any], direction: str, relation: str) -> dict[str, Any]:
    contribution = _float(part["contribution"])
    effect = "상승 요인" if contribution > 0 else "하락 요인" if contribution < 0 else "중립"
    if relation == "supporting" and direction in {"up", "down"}:
        effect = f"{DIRECTION_LABELS.get(direction, direction)} 판단 지지"
    elif relation == "offsetting" and direction in {"up", "down"}:
        effect = f"{DIRECTION_LABELS.get(direction, direction)} 판단 약화"
    return {
        "feature": part["feature"],
        "label": part["label"],
        "effect": effect,
        "raw_value": _round(part["raw_value"]),
        "training_mean": _round(part["mean"]),
        "z_score": _round(part["z_score"]),
        "coefficient": _round(part["coefficient"]),
        "contribution": _round(contribution),
        "contribution_pct_points": _round(contribution * 100.0),
    }


def _quality_snapshot(quality: dict[str, Any]) -> dict[str, Any]:
    if not quality:
        return {}
    return {
        "promotion_status": quality.get("promotion_status"),
        "hold_reasons": quality.get("hold_reasons", []),
        "test_direction_accuracy": _round(quality.get("test_direction_accuracy")),
        "backtest_direction_accuracy": _round(quality.get("backtest_direction_accuracy")),
        "confidence": quality.get("confidence"),
    }


def _held_horizons(predictions: dict[str, Any], quality_by_horizon: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    held = []
    for run in predictions.get("runs", []):
        if not isinstance(run, dict) or run.get("status") != "skipped_by_quality_gate":
            continue
        horizon = int(run["horizon_days"])
        quality = quality_by_horizon.get(horizon, {})
        held.append(
            {
                "horizon_days": horizon,
                "promotion_status": run.get("promotion_status"),
                "hold_reasons": run.get("hold_reasons", []),
                "quality_gate": _quality_snapshot(quality),
            }
        )
    return held


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _round(value: Any) -> float:
    return round(_float(value), 6)


if __name__ == "__main__":
    raise SystemExit(main())
