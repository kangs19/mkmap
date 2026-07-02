from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select
from app.database import get_db
from app.models.item import Item
from app.models.forecast import Forecast
from app.models.price import DailyPrice
from app.models.signal import RegionSignal
from app.schemas.forecast import ForecastResponse, TopFactor
from datetime import date
from app.timezone import kst_today

router = APIRouter(prefix="/api/v1/items", tags=["forecasts"])


@router.get("/{item_code}/forecast", response_model=ForecastResponse)
async def get_forecast(
    item_code: str,
    target_date: str = None,
    horizon: int = 14,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404
        })

    base_date = date.fromisoformat(target_date) if target_date else kst_today()

    fc_result = await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
            Forecast.horizon_days == horizon,
        ).order_by(Forecast.created_at.desc())
    )
    fc = fc_result.scalar_one_or_none()

    if not fc:
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜 horizon={horizon}일 예측 데이터가 없습니다.",
            "code": 404
        })

    direction = fc.direction or fc.direction_14d
    up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d

    return ForecastResponse(
        item_code=fc.item_code,
        item_name=item.item_name,
        base_date=str(fc.base_date),
        model_version=fc.model_version,
        model_scope=_model_scope(fc),
        forecast={
            "horizon_days": fc.horizon_days,
            "direction": direction,
            "up_probability": up_prob,
            "direction_14d": fc.direction_14d,
            "up_probability_14d": fc.up_probability_14d,
            "surge_probability_14d": fc.surge_probability_14d,
            "volatility_risk_30d": fc.volatility_risk_30d,
            "bottom_probability": fc.bottom_probability,
        },
        top_factors=[TopFactor(**f) for f in (fc.top_factors or [])],
        national_supply_shock=fc.national_supply_shock,
        confidence=fc.confidence,
        summary=_build_summary(fc, item.item_name, horizon),
    )


@router.get("/{item_code}/forecasts")
async def get_all_horizons(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    """14/30/60/90일 예측을 한 번에 반환."""
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={"error": "item_not_found", "code": 404})

    base_date = date.fromisoformat(target_date) if target_date else kst_today()

    fc_rows = (await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
        ).order_by(Forecast.horizon_days)
    )).scalars().all()

    if not fc_rows:
        raise HTTPException(status_code=404, detail={
            "error": "forecast_not_found",
            "message": f"'{base_date}' 날짜의 예측 데이터가 없습니다.",
            "code": 404,
        })

    horizons = {}
    for fc in fc_rows:
        insufficient = fc.confidence == "insufficient_data"
        direction = fc.direction or fc.direction_14d
        up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d
        horizons[str(fc.horizon_days)] = {
            "horizon_days": fc.horizon_days,
            "available": not insufficient,
            "data_status": "insufficient_data" if insufficient else "ok",
            "direction": None if insufficient else direction,
            "up_probability": None if insufficient else up_prob,
            "bottom_probability": None if insufficient else fc.bottom_probability,
            "confidence": fc.confidence,
            "model_version": fc.model_version,
        }

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "base_date": str(base_date),
        "horizons": horizons,
    }


def _build_summary(fc: Forecast, item_name: str, horizon: int = 14) -> str:
    direction_map = {"up": "상승", "down": "하락", "neutral": "보합"}
    direction = direction_map.get(fc.direction or fc.direction_14d or "", "불명확")
    up_prob = fc.up_probability if fc.up_probability is not None else fc.up_probability_14d
    prob = int((up_prob or 0) * 100)
    label = {7: "1주", 14: "2주", 21: "3주", 28: "4주", 60: "2개월", 90: "3개월"}.get(horizon, f"{horizon}일")
    last = item_name[-1] if item_name else ""
    code = ord(last) - 0xAC00
    eun_neun = "은" if (0 <= code < 11172 and code % 28 != 0) else "는"
    return f"{item_name}{eun_neun} {label} 내 {direction} 가능성이 {prob}%입니다."


def _model_scope(fc: Forecast) -> str:
    for factor in fc.top_factors or []:
        if not isinstance(factor, dict):
            continue
        name = str(factor.get("factor") or "")
        if name.startswith("model_scope_"):
            return name.replace("model_scope_", "", 1)
    if fc.model_version and fc.model_version.endswith("_item"):
        return "item"
    return "global"


_CROP_STATIC = {
    "cabbage": {
        "headline": "배추 — 고랭지·평야 출하 교체기 가격 변동 주의",
        "reasons": [
            {"label": "계절성 출하 패턴", "direction": "up", "direction_label": "↑ 상승 요인",
             "description": "7~8월 강원 고랭지 배추 대량 출하로 일시 가격 하락 후, 9~11월 김장철 수요 급증으로 반등합니다."},
            {"label": "기상 리스크", "direction": "up", "direction_label": "↑ 상승 요인",
             "description": "폭염·집중호우 시 단기 생육 피해로 출하량이 감소하여 가격이 급등할 수 있습니다."},
            {"label": "재배면적 변화", "direction": "neutral", "direction_label": "→ 중립",
             "description": "전년도 가격 수준에 따라 농가 파종 면적이 조정되며 다음 시즌 공급량에 영향을 줍니다."},
        ],
        "notes": ["김장철(10~11월) 수요 집중으로 가을 가격 변동폭이 큽니다.", "고랭지 생산지 기상 이슈는 단기 급등의 주요 트리거입니다."],
    },
    "radish": {
        "headline": "무 — 봄·가을 출하 집중으로 계절 가격 차이 발생",
        "reasons": [
            {"label": "출하 계절성", "direction": "neutral", "direction_label": "→ 계절 패턴",
             "description": "봄무(4~5월)와 가을무(9~10월) 2회 집중 출하 시즌이 있으며 여름·겨울엔 공급 부족으로 가격이 오릅니다."},
            {"label": "산지 기상", "direction": "up", "direction_label": "↑ 위험 요인",
             "description": "여름 폭염 시 생육 장해가 발생하여 가을 공급량이 감소할 수 있습니다."},
        ],
        "notes": ["여름 공급 감소 시기 가격 상승에 주의하세요."],
    },
    "onion": {
        "headline": "양파 — 저장량·수입 동향이 연중 가격을 결정",
        "reasons": [
            {"label": "저장 재고량", "direction": "neutral", "direction_label": "→ 핵심 변수",
             "description": "5~6월 수확 후 냉동 저장량에 따라 연말까지 가격이 결정됩니다. 재고 부족 시 급등 리스크가 높아집니다."},
            {"label": "수입 경쟁", "direction": "down", "direction_label": "↓ 하락 요인",
             "description": "국내 가격 급등 시 중국산 양파 수입이 증가하여 가격을 안정시키는 경향이 있습니다."},
            {"label": "산지 작황", "direction": "up", "direction_label": "↑ 위험 요인",
             "description": "전남·경남 주산지 봄철 가뭄·냉해는 단수 감소로 이어져 저장량 부족을 초래합니다."},
        ],
        "notes": ["수확기(5~6월) 저장량 발표가 연간 가격 전망의 핵심 지표입니다.", "관세 동향과 수입 물량도 모니터링이 필요합니다."],
    },
    "green_onion": {
        "headline": "대파 — 기상 민감도 최상, 단기 가격 변동폭 큼",
        "reasons": [
            {"label": "기상 민감도", "direction": "up", "direction_label": "↑ 최대 위험",
             "description": "대파는 한파·폭염에 매우 민감해 기상 충격 후 2~3주 내에 가격이 2~3배 급등하는 사례가 빈번합니다."},
            {"label": "단경기 공급 부족", "direction": "up", "direction_label": "↑ 계절 리스크",
             "description": "7~8월 여름철 국내 생산 감소 시기에 단경기 가격 상승이 나타납니다."},
            {"label": "시설재배 완충", "direction": "down", "direction_label": "↓ 완화 요인",
             "description": "겨울철 시설 대파 생산이 확대되어 극단적 가격 급등을 일부 억제합니다."},
        ],
        "notes": ["대파는 단기(1~2주) 예측 신뢰도가 장기 예측보다 높습니다.", "기상청 한파·폭염 경보 발령 시 즉시 상승 신호로 해석하세요."],
    },
    "garlic": {
        "headline": "마늘 — 연산 재고와 중국 수입이 가격의 양대 축",
        "reasons": [
            {"label": "저장 재고", "direction": "neutral", "direction_label": "→ 핵심 변수",
             "description": "6월 수확 후 저장 물량이 다음 해 5월까지 공급을 결정합니다. 재고율이 전년 대비 낮으면 연중 강세입니다."},
            {"label": "중국산 수입", "direction": "down", "direction_label": "↓ 하락 요인",
             "description": "국내 산지가격이 kg당 3,000원을 초과하면 중국산 수입 확대로 가격이 조정됩니다."},
            {"label": "주산지 작황", "direction": "up", "direction_label": "↑ 위험 요인",
             "description": "경북 의성·전남 해남의 봄철 가뭄은 단수에 직접 영향을 줍니다."},
        ],
        "notes": ["마늘은 1년 단위로 수급이 결정되는 특성상 장기(2~3개월) 예측 활용도가 높습니다."],
    },
    "potato": {
        "headline": "감자 — 봄·여름 출하 집중, 저장성으로 연중 공급 가능",
        "reasons": [
            {"label": "출하 시기 집중", "direction": "neutral", "direction_label": "→ 계절 패턴",
             "description": "제주(4~5월), 내륙(6~7월) 봄감자 집중 출하 시 가격이 낮아지고 가을~겨울은 상대적 강세입니다."},
            {"label": "저장 기술 발달", "direction": "down", "direction_label": "↓ 가격 안정화",
             "description": "CA 저장 보급으로 연중 공급이 가능해져 과거 대비 계절 가격 편차가 줄고 있습니다."},
        ],
        "notes": ["수미감자와 두백감자 품종별 출하 시기 차이가 있습니다."],
    },
    "pepper": {
        "headline": "건고추 — 수확 연도·작황이 연간 가격 수준 결정",
        "reasons": [
            {"label": "연산 작황", "direction": "up", "direction_label": "↑ 핵심 요인",
             "description": "경북·충남 주산지 여름 폭염과 탄저병은 건고추 작황에 결정적 영향을 미칩니다."},
            {"label": "수입 중국고추", "direction": "down", "direction_label": "↓ 경쟁 요인",
             "description": "국내 가격 강세 시 중국산 고추 수입이 증가하여 가격 상승폭을 제한합니다."},
        ],
        "notes": ["건고추는 수확 후 저장 물량이 다음 해까지 영향을 주므로 장기 예측이 중요합니다."],
    },
    "tomato": {
        "headline": "토마토 — 시설재배 중심, 에너지 비용과 기상이 주요 변수",
        "reasons": [
            {"label": "시설 에너지 비용", "direction": "up", "direction_label": "↑ 비용 압박",
             "description": "겨울 시설재배 난방비 증가는 생산원가를 높여 1~2월 가격 상승으로 이어집니다."},
            {"label": "여름 노지 경쟁", "direction": "down", "direction_label": "↓ 공급 증가",
             "description": "6~8월 노지·반시설 토마토 대량 출하로 가격이 하락하는 경향이 있습니다."},
        ],
        "notes": ["토마토는 저장성이 낮아 단기 수급 균형이 가격에 빠르게 반영됩니다."],
    },
    "apple": {
        "headline": "사과 — 저장 재고와 기상(우박·냉해)이 연간 가격 결정",
        "reasons": [
            {"label": "냉해·우박 피해", "direction": "up", "direction_label": "↑ 최대 리스크",
             "description": "봄철 냉해와 여름 우박은 경북 주산지 착과율을 낮춰 연간 가격 급등의 주요 원인이 됩니다."},
            {"label": "저장 물량", "direction": "neutral", "direction_label": "→ 연중 공급",
             "description": "CA 저장된 물량이 이듬해 7월까지 공급되어 신구과 교체 시기인 7~8월에 가격 변동이 큽니다."},
            {"label": "재배면적 트렌드", "direction": "up", "direction_label": "↑ 장기 위험",
             "description": "기후 변화로 사과 주산지가 북상하면서 생산 안정성이 낮아지는 추세입니다."},
        ],
        "notes": ["사과는 해거리(격년 풍·흉작) 패턴이 있어 전년 작황 확인이 중요합니다."],
    },
    "strawberry": {
        "headline": "딸기 — 겨울 시설 출하 집중, 기온과 에너지 비용이 핵심",
        "reasons": [
            {"label": "출하 시기", "direction": "neutral", "direction_label": "→ 계절 패턴",
             "description": "12~4월 국내산 딸기 출하 성수기이며, 5~11월은 공급 부족으로 가격이 높습니다."},
            {"label": "겨울 기온", "direction": "up", "direction_label": "↑ 날씨 민감",
             "description": "성수기인 12~2월 한파 강도는 생육 속도와 출하량에 직접 영향을 줍니다."},
        ],
        "notes": ["딸기는 수출 비중이 높아져 원화 환율과 일본 수요도 가격 변수가 됩니다."],
    },
}
_CROP_STATIC_DEFAULT = {
    "reasons": [
        {"label": "계절적 수급 패턴", "direction": "neutral", "direction_label": "→ 분석 중",
         "description": "해당 작물의 생산 주기와 계절 수급 패턴을 AI가 학습하여 가격 방향을 예측합니다."},
        {"label": "기상 리스크", "direction": "up", "direction_label": "↑ 주요 변수",
         "description": "주산지 기상 이상(폭염·한파·집중호우)은 단기 공급 충격으로 가격 급등의 트리거가 됩니다."},
        {"label": "전국 도매 시세 추이", "direction": "neutral", "direction_label": "→ 추적 중",
         "description": "가락시장 등 주요 도매시장의 일일 거래량과 평균가를 기반으로 가격 추세를 분석합니다."},
    ],
    "notes": ["예측 데이터는 파이프라인 실행 후 자동 업데이트됩니다.", "현재는 모델 구조 설명 기반 정보를 제공합니다."],
}


@router.get("/{item_code}/forecast/explanation")
async def get_forecast_explanation(
    item_code: str,
    target_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    item, fc, base_date = await _load_item_forecast(item_code, target_date, db)
    latest_price_date = (
        await db.execute(
            select(func.max(DailyPrice.date)).where(DailyPrice.item_code == item_code)
        )
    ).scalar()
    latest_signal_date = (
        await db.execute(
            select(func.max(RegionSignal.date)).where(RegionSignal.item_code == item_code)
        )
    ).scalar()

    # fc 없을 때 — 작물별 정적 설명 반환
    if fc is None:
        static = _CROP_STATIC.get(item_code, _CROP_STATIC_DEFAULT)
        return {
            "item_code": item_code,
            "item_name": item.item_name,
            "base_date": str(base_date),
            "headline": static.get("headline", f"{item.item_name} — AI 예측 모델 구조 설명"),
            "model": {
                "version": "static",
                "scope": "item",
                "scope_label": "모델 설명 (예측 데이터 준비 중)",
                "confidence": "medium",
                "confidence_label": "보통",
                "confidence_reason": "파이프라인 실행 전 정적 설명입니다. 실제 예측은 관리자 파이프라인 실행 후 업데이트됩니다.",
                "confidence_factors": [],
            },
            "forecast": {
                "direction_14d": None,
                "direction_label": "예측 준비 중",
                "up_probability_14d": None,
                "up_probability_label": "—",
                "surge_probability_14d": None,
                "volatility_risk_30d": None,
                "bottom_probability": None,
                "national_supply_shock": None,
            },
            "reasons": static.get("reasons", _CROP_STATIC_DEFAULT["reasons"]),
            "risk_regions": [],
            "data_freshness": {
                "price": _freshness(latest_price_date, base_date, warn_after_days=2),
                "region_signal": _freshness(latest_signal_date, base_date, warn_after_days=1),
                "forecast": {"status": "missing", "status_label": "예측 없음", "latest_date": None},
            },
            "notes": static.get("notes", _CROP_STATIC_DEFAULT["notes"]),
            "disclaimer": ForecastResponse.model_fields["disclaimer"].default,
        }

    model_scope = _model_scope(fc)
    signal_result = await db.execute(
        select(RegionSignal)
        .where(RegionSignal.item_code == item_code, RegionSignal.date == base_date)
        .order_by(desc(RegionSignal.risk_score))
        .limit(3)
    )

    reasons = [_factor_reason(factor) for factor in (fc.top_factors or [])]
    # top_factors 없으면 정적 데이터로 보완
    if not reasons:
        static = _CROP_STATIC.get(item_code, _CROP_STATIC_DEFAULT)
        reasons = static.get("reasons", _CROP_STATIC_DEFAULT["reasons"])

    return {
        "item_code": fc.item_code,
        "item_name": item.item_name,
        "base_date": str(fc.base_date),
        "headline": _build_explanation_headline(fc, item.item_name),
        "model": {
            "version": fc.model_version,
            "scope": model_scope,
            "scope_label": "품목 전용 모델" if model_scope == "item" else "공통 모델",
            "confidence": fc.confidence,
            "confidence_label": _confidence_label(fc.confidence),
            "confidence_reason": _confidence_reason(fc, model_scope, latest_price_date, latest_signal_date, base_date),
            "confidence_factors": _confidence_factors(fc, model_scope, latest_price_date, latest_signal_date, base_date),
        },
        "forecast": {
            "direction_14d": fc.direction_14d,
            "direction_label": _direction_label(fc.direction_14d),
            "up_probability_14d": fc.up_probability_14d,
            "up_probability_label": _percent_label(fc.up_probability_14d),
            "surge_probability_14d": fc.surge_probability_14d,
            "volatility_risk_30d": fc.volatility_risk_30d,
            "bottom_probability": fc.bottom_probability,
            "national_supply_shock": fc.national_supply_shock,
        },
        "reasons": reasons,
        "risk_regions": [_risk_region(region) for region in signal_result.scalars().all()],
        "data_freshness": {
            "price": _freshness(latest_price_date, base_date, warn_after_days=2),
            "region_signal": _freshness(latest_signal_date, base_date, warn_after_days=1),
            "forecast": _freshness(fc.base_date, base_date, warn_after_days=1),
        },
        "notes": _explanation_notes(model_scope, latest_price_date, latest_signal_date, base_date),
        "disclaimer": ForecastResponse.model_fields["disclaimer"].default,
    }


async def _load_item_forecast(
    item_code: str,
    target_date: str | None,
    db: AsyncSession,
    horizon: int = 14,
) -> tuple[Item, "Forecast | None", date]:
    result = await db.execute(select(Item).where(Item.item_code == item_code))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail={
            "error": "item_not_found",
            "message": f"품목 코드 '{item_code}'를 찾을 수 없습니다.",
            "code": 404,
        })

    base_date = date.fromisoformat(target_date) if target_date else kst_today()
    fc_result = await db.execute(
        select(Forecast).where(
            Forecast.item_code == item_code,
            Forecast.base_date == base_date,
            Forecast.horizon_days == horizon,
        ).order_by(Forecast.created_at.desc())
    )
    fc = fc_result.scalar_one_or_none()
    # 오늘 데이터 없으면 가장 최근 예측으로 fallback
    if not fc:
        fallback = await db.execute(
            select(Forecast).where(
                Forecast.item_code == item_code,
                Forecast.horizon_days == horizon,
            ).order_by(Forecast.base_date.desc(), Forecast.created_at.desc()).limit(1)
        )
        fc = fallback.scalar_one_or_none()
    # fc=None이어도 item과 base_date는 반환 (호출부가 처리)
    return item, fc, fc.base_date if fc else base_date


def _direction_label(direction: str | None) -> str:
    return {"up": "상승", "down": "하락", "neutral": "보합"}.get(direction or "", "불확실")


def _confidence_label(confidence: str | None) -> str:
    return {"high": "높음", "medium": "보통", "low": "낮음"}.get(confidence or "", "보통")


def _confidence_reason(
    fc: Forecast,
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> str:
    factors = _confidence_factors(fc, model_scope, latest_price_date, latest_signal_date, base_date)
    weak_factors = [factor for factor in factors if factor["status"] in {"weak", "missing"}]
    if fc.confidence == "high" and not weak_factors:
        return "Backtest calibration and current inputs support a high-confidence forecast."
    if weak_factors:
        labels = ", ".join(str(factor["label"]) for factor in weak_factors[:2])
        return f"Confidence is limited by {labels}."
    if fc.confidence == "medium":
        return "Forecast inputs are usable, but uncertainty remains in the recent signal mix."
    return "Confidence is conservative until more recent item-level history is available."


def _confidence_factors(
    fc: Forecast,
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> list[dict[str, str]]:
    price_status = _freshness(latest_price_date, base_date, warn_after_days=2)["status"]
    signal_status = _freshness(latest_signal_date, base_date, warn_after_days=1)["status"]
    risk_factor_count = sum(
        1
        for factor in (fc.top_factors or [])
        if isinstance(factor, dict) and str(factor.get("factor") or "") != "price_lag_model"
    )
    return [
        {
            "key": "model_scope",
            "label": "item model" if model_scope == "item" else "global model",
            "status": "strong" if model_scope == "item" else "medium",
        },
        {
            "key": "price_freshness",
            "label": "price data freshness",
            "status": "strong" if price_status == "fresh" else ("weak" if price_status == "stale" else "missing"),
        },
        {
            "key": "signal_freshness",
            "label": "risk signal freshness",
            "status": "strong" if signal_status == "fresh" else ("weak" if signal_status == "stale" else "missing"),
        },
        {
            "key": "risk_context",
            "label": "risk context",
            "status": "strong" if risk_factor_count > 0 else "weak",
        },
    ]


def _percent_label(value: float | None) -> str:
    if value is None:
        return "정보 없음"
    return f"{round(value * 100)}%"


def _build_explanation_headline(fc: Forecast, item_name: str) -> str:
    return (
        f"{item_name}은 향후 14일 기준 {_direction_label(fc.direction_14d)} 가능성이 "
        f"{_percent_label(fc.up_probability_14d)}로 계산되었습니다."
    )


def _factor_reason(factor: dict) -> dict:
    name = str(factor.get("factor") or "")
    direction = str(factor.get("direction") or "up")
    contribution = float(factor.get("contribution") or 0.0)
    label_map = {
        "price_lag_model": "최근 가격 흐름",
        "risk_overlay": "주산지 위험 보정",
    }
    message_map = {
        ("price_lag_model", "up"): "최근 가격 흐름이 상승 쪽으로 기울었습니다.",
        ("price_lag_model", "down"): "최근 가격 흐름이 하락 쪽으로 기울었습니다.",
        ("risk_overlay", "up"): "주산지 위험 신호가 가격 상승 압력을 더했습니다.",
        ("risk_overlay", "down"): "주산지 위험 신호가 가격 상승 압력을 낮췄습니다.",
    }
    return {
        "factor": name,
        "label": label_map.get(name, name or "기타 요인"),
        "direction": direction,
        "direction_label": _direction_label(direction),
        "contribution": contribution,
        "message": message_map.get((name, direction), "모델 계산에 반영된 요인입니다."),
    }


def _risk_region(region: RegionSignal) -> dict:
    return {
        "region_code": region.region_code,
        "region_name": region.region_name,
        "risk_score": region.risk_score,
        "risk_level": region.risk_level,
        "price_effect": region.price_effect,
        "summary": region.summary_text,
    }


def _freshness(latest_date: date | None, base_date: date, warn_after_days: int) -> dict:
    if latest_date is None:
        return {
            "latest_date": None,
            "lag_days": None,
            "status": "missing",
            "warn_after_days": warn_after_days,
        }
    lag_days = (base_date - latest_date).days
    if lag_days <= warn_after_days:
        status = "fresh"
    elif lag_days <= warn_after_days + 2:
        status = "stale"
    else:
        status = "missing"
    return {
        "latest_date": str(latest_date),
        "lag_days": lag_days,
        "status": status,
        "warn_after_days": warn_after_days,
    }


def _explanation_notes(
    model_scope: str,
    latest_price_date: date | None,
    latest_signal_date: date | None,
    base_date: date,
) -> list[str]:
    notes = []
    if model_scope == "global":
        notes.append("아직 품목 전용 모델보다 공통 모델의 검증 성능이 더 안정적이어서 공통 모델을 사용했습니다.")
    else:
        notes.append("해당 품목의 검증 성능 기준을 통과한 품목 전용 모델을 사용했습니다.")
    if latest_price_date and latest_price_date < base_date:
        notes.append(f"가격 데이터 최신일은 {latest_price_date}로, 기준일보다 {(base_date - latest_price_date).days}일 늦습니다.")
    if latest_signal_date and latest_signal_date < base_date:
        notes.append(f"주산지 위험 신호 최신일은 {latest_signal_date}입니다.")
    return notes
