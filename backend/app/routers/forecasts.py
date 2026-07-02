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


def _horizon_phase(days: int) -> str:
    """7~21일=단기(short), 28~60일=중기(medium), 90일=장기(long)"""
    if days <= 21:
        return "short"
    if days <= 60:
        return "medium"
    return "long"

# 작물별 × 기간별(단기/중기/장기) 상승/하락 이유 데이터
# reasons: {phase: [{label, direction, direction_label, description}]}
# notes:   {phase: [str]}
_CROP_STATIC: dict = {
    "cabbage": {
        "headline": "배추 — 고랭지·평야 출하 교체기, 김장철 수요 예측",
        "reasons": {
            "short": [
                {"label": "산지 기상 충격", "direction": "up", "direction_label": "↑ 단기 급등 리스크",
                 "description": "폭염·집중호우·냉해 발생 시 생육 피해가 1~3주 내 출하량 감소로 이어져 가격이 빠르게 반응합니다."},
                {"label": "현재 출하 수준", "direction": "neutral", "direction_label": "→ 출하 동향 주시",
                 "description": "가락시장 일일 입하량과 평균 경락가를 기반으로 1~2주 수급 균형을 평가합니다. 입하 감소 시 즉시 상승 신호입니다."},
                {"label": "도매시장 재고 회전", "direction": "neutral", "direction_label": "→ 단기 지표",
                 "description": "산지-도매 간 반입 시차(2~5일)를 감안할 때, 산지 작황 변화는 1주일 내 시장가에 반영됩니다."},
            ],
            "medium": [
                {"label": "고랭지→평야 출하 교체", "direction": "up", "direction_label": "↑ 공급 절벽 위험",
                 "description": "강원 고랭지 배추(7~9월)가 마감되는 9월 말~10월 초, 가을 평야지 배추 출하 전 공백기에 가격이 상승합니다."},
                {"label": "김장 수요 선반영", "direction": "up", "direction_label": "↑ 수요 압박",
                 "description": "소비자와 도매업체가 2개월 후 김장 성수기를 앞두고 선 매입을 늘리면서 시세가 선행 상승합니다."},
                {"label": "전국 재배면적 통계", "direction": "neutral", "direction_label": "→ 공급 예측 변수",
                 "description": "농촌진흥청 작황 조사(월별)에서 나타나는 전국 생산 예상량이 2개월 후 가격 방향을 결정합니다."},
            ],
            "long": [
                {"label": "김장철 수요 집중", "direction": "up", "direction_label": "↑ 연간 최대 수요기",
                 "description": "10~11월 전국 가정의 김장 담그기가 집중되면서 배추 수요가 연간 최고점에 달합니다. 이 시기 공급이 부족하면 가격이 급등합니다."},
                {"label": "겨울 공급 감소", "direction": "up", "direction_label": "↑ 계절적 가격 상승",
                 "description": "12월 이후 노지 생산이 중단되고 시설·저장 물량으로만 공급이 유지되어 가격 강세가 지속됩니다."},
                {"label": "전년 파종 면적 피드백", "direction": "neutral", "direction_label": "→ 장기 공급 조정",
                 "description": "금년 가격이 높으면 내년 농가 파종 면적이 증가해 가격 하락 압력이 생기는 사이클이 반복됩니다."},
            ],
        },
        "notes": {
            "short": ["단기 예측은 기상 정보가 가장 중요합니다. 기상청 폭염·한파 특보를 함께 모니터링하세요."],
            "medium": ["고랭지 출하 마감 시점(9월 말)과 가을배추 출하 시작(10월 초)의 시차가 가격 변동성을 결정합니다."],
            "long": ["3개월 예측은 김장철 수요와 산지 재배 계획 기반으로 방향성을 제시합니다. 실제 가격은 기상·수출입에 따라 조정될 수 있습니다."],
        },
    },
    "radish": {
        "headline": "무 — 봄·가을 2회 출하 집중, 여름 단경기 주의",
        "reasons": {
            "short": [
                {"label": "단경기 공급 부족", "direction": "up", "direction_label": "↑ 단기 상승 리스크",
                 "description": "여름(7~8월) 봄무 출하 종료 후 가을무 출하 전까지 공급 공백이 생겨 1~2주 내 가격이 오릅니다."},
                {"label": "기상 충격 반응", "direction": "up", "direction_label": "↑ 즉각 반응",
                 "description": "폭염·침수로 인한 산지 피해는 일주일 내 가락시장 입하량 감소로 나타나 단기 급등 트리거가 됩니다."},
            ],
            "medium": [
                {"label": "가을무 출하 준비 상황", "direction": "down", "direction_label": "↓ 공급 회복 신호",
                 "description": "전남 해남·제주 가을무(9~10월)의 파종·생육 상황에 따라 2개월 후 공급 회복 여부가 결정됩니다."},
                {"label": "저장 유통 비중", "direction": "neutral", "direction_label": "→ 완충 역할",
                 "description": "무는 저장성이 비교적 높아 여름 단경기 중에도 저장 물량이 가격 급등을 일부 완화합니다."},
            ],
            "long": [
                {"label": "김장무 수요", "direction": "up", "direction_label": "↑ 계절 수요 집중",
                 "description": "11월 김장철 깍두기·총각김치 재료 수요로 무 가격이 연중 최고 수준에 오르는 계절 패턴이 있습니다."},
                {"label": "재배 의향 면적", "direction": "neutral", "direction_label": "→ 장기 공급 결정",
                 "description": "금년 봄·가을 가격 수준이 다음 시즌 농가 파종 면적을 결정해 장기 공급량을 좌우합니다."},
            ],
        },
        "notes": {
            "short": ["여름 단경기(7~8월)는 무 가격 최대 급등 시기입니다. 이 시기 기상 이상에 특히 주의하세요."],
            "medium": ["가을무 생육 진행 상황을 산지 작황 조사로 확인하면 2개월 예측 정확도를 높일 수 있습니다."],
            "long": ["3개월 전망은 김장 수요기와 일치할 가능성이 높아 계절 상승 편향이 반영됩니다."],
        },
    },
    "onion": {
        "headline": "양파 — 연산 저장 재고와 수입이 연중 가격을 지배",
        "reasons": {
            "short": [
                {"label": "산지 출하 동향", "direction": "neutral", "direction_label": "→ 단기 수급 지표",
                 "description": "전남·경남 주산지에서 일일 출하되는 물량과 가락시장 경락가를 통해 1~2주 수급 흐름을 파악합니다."},
                {"label": "저장 이행 물량", "direction": "down", "direction_label": "↓ 가격 안정화",
                 "description": "5~6월 수확 직후 저온저장으로 이행되는 물량이 많을수록 단기 시장 공급이 줄어들어 가격이 지지됩니다."},
            ],
            "medium": [
                {"label": "저장 재고 소진율", "direction": "up", "direction_label": "↑ 2개월 핵심 변수",
                 "description": "7~8월 저장 재고 소진이 예상보다 빠르면 2개월 내 공급 부족으로 가격 급등 리스크가 높아집니다."},
                {"label": "수입 동향", "direction": "down", "direction_label": "↓ 가격 억제",
                 "description": "국내 가격 상승 시 정부·민간의 중국산 양파 수입 확대 결정이 2~4주 내 효과를 나타냅니다."},
            ],
            "long": [
                {"label": "연산 재고율", "direction": "neutral", "direction_label": "→ 장기 가격 결정자",
                 "description": "수확 후 저장 물량이 다음 해 5월 신규 수확 전까지 공급을 책임집니다. 재고율이 전년 대비 낮으면 연중 강세입니다."},
                {"label": "봄철 파종 면적", "direction": "down", "direction_label": "↓ 내년 공급 신호",
                 "description": "금년 가격이 높으면 이듬해 봄 파종 면적이 증가하여 내년 가격 하락 압력이 생기는 사이클이 있습니다."},
                {"label": "중국 작황·환율", "direction": "neutral", "direction_label": "→ 수입가 변수",
                 "description": "중국산 양파 수입가격은 중국 현지 작황과 원/위안 환율에 따라 결정되어 국내 가격의 상한선 역할을 합니다."},
            ],
        },
        "notes": {
            "short": ["양파 단기 가격은 현재 저장 출하 속도와 가락시장 경락가를 실시간 모니터링하는 것이 핵심입니다."],
            "medium": ["정부 비축 방출·수입 결정 타이밍이 2개월 가격을 크게 흔들 수 있습니다."],
            "long": ["저장 재고율과 중국산 수입 물량이 3개월 가격 전망의 양대 축입니다."],
        },
    },
    "green_onion": {
        "headline": "대파 — 기상 민감도 1위, 단기 예측 신뢰도 가장 높음",
        "reasons": {
            "short": [
                {"label": "기상 즉각 반응", "direction": "up", "direction_label": "↑ 1~2주 급등 위험",
                 "description": "한파·폭설·폭염 발생 시 대파는 농산물 중 가장 빠르게 반응해 1~2주 내에 50~200% 가격 급등 사례가 많습니다."},
                {"label": "시장 출하 집중도", "direction": "neutral", "direction_label": "→ 단기 수급 현황",
                 "description": "전남 진도·경기 수원 등 주산지 당일 출하 물량이 단기 가격의 직접 결정 변수입니다."},
                {"label": "대체품 부재", "direction": "up", "direction_label": "↑ 수요 경직",
                 "description": "국내 조리문화상 대파의 대체 식재료가 없어 공급 감소 시 소비 감소 없이 가격이 직접 오릅니다."},
            ],
            "medium": [
                {"label": "여름 단경기", "direction": "up", "direction_label": "↑ 계절 상승 구간",
                 "description": "7~8월 여름 고온으로 대파 생육이 둔화되고 출하량이 줄어드는 연간 단경기가 2개월 가격 상승 패턴을 만듭니다."},
                {"label": "산지 파종 동향", "direction": "down", "direction_label": "↓ 공급 회복 신호",
                 "description": "가격 상승 후 2개월 내 농가 추가 파종이 늘어나 공급 회복으로 가격이 안정화되는 흐름이 나타납니다."},
            ],
            "long": [
                {"label": "겨울 시설 생산 확대", "direction": "down", "direction_label": "↓ 공급 안정화",
                 "description": "온실·터널 시설 대파 재배 확대로 겨울 공급 부족이 줄어들어 과거 대비 가격 변동폭이 낮아지는 추세입니다."},
                {"label": "계절 수요 패턴", "direction": "neutral", "direction_label": "→ 연중 소비 균등",
                 "description": "대파는 연중 소비량이 비교적 균등해 수요 측 계절성보다 공급 측 변동이 가격을 주로 결정합니다."},
            ],
        },
        "notes": {
            "short": ["대파는 단기 예측이 가장 정확한 작물입니다. 기상청 특보 발령을 최우선 지표로 활용하세요."],
            "medium": ["여름(7~8월)은 대파 단경기로 연간 가장 높은 가격대가 형성되는 시기입니다."],
            "long": ["3개월 전망 시 시설 재배 확대 추세를 감안하면 과거 대비 급등 리스크가 다소 줄었습니다."],
        },
    },
    "garlic": {
        "headline": "마늘 — 연산 저장 재고와 중국 수입이 양대 가격 결정 변수",
        "reasons": {
            "short": [
                {"label": "산지 출하가", "direction": "neutral", "direction_label": "→ 현재 수급",
                 "description": "경북 의성·전남 해남 등 주산지에서 실제 거래되는 밭떼기 가격이 단기 도매시장 가격을 선행합니다."},
                {"label": "냉동마늘 방출", "direction": "down", "direction_label": "↓ 단기 공급 완충",
                 "description": "정부 비축 냉동마늘의 시장 방출 결정이 발표 후 1~2주 내 가격을 즉각 하락시킵니다."},
            ],
            "medium": [
                {"label": "저장 재고 소진 속도", "direction": "up", "direction_label": "↑ 재고 감소 위험",
                 "description": "6월 수확 후 저장 물량이 예상보다 빠르게 소진되면 2~3개월 내 공급 부족으로 가격이 오릅니다."},
                {"label": "수입 마늘 통관", "direction": "down", "direction_label": "↓ 수입 억제 효과",
                 "description": "중국산 마늘 수입 관세(360%)로 평상시 수입이 제한되지만 가격 급등 시 관세 인하나 TRQ 활용으로 수입이 늘 수 있습니다."},
            ],
            "long": [
                {"label": "당해 재고율 전망", "direction": "neutral", "direction_label": "→ 장기 핵심 지표",
                 "description": "6월 수확 시즌 생산량과 저장 이행량이 다음 해 5월까지 연중 공급량을 결정합니다. 재고율 70% 미만이면 강세 신호입니다."},
                {"label": "파종 면적 증감", "direction": "down", "direction_label": "↓ 내년 공급 조정",
                 "description": "금년 가격이 높으면 다음 해 가을 파종 면적이 늘어나 이듬해 수확기 공급 과잉과 가격 하락이 예상됩니다."},
                {"label": "중국 작황·수출 동향", "direction": "neutral", "direction_label": "→ 수입가 변수",
                 "description": "중국 마늘 생산량과 수출 정책이 국내 수입 가능 가격과 물량을 결정하여 장기 국내가격에 영향을 줍니다."},
            ],
        },
        "notes": {
            "short": ["마늘은 단기 거래량보다 정부 정책(비축 방출·수입 결정)이 가격에 빠르게 영향을 줍니다."],
            "medium": ["7~9월 저장 마늘 소진 속도가 연말 가격을 예측하는 핵심 지표입니다."],
            "long": ["마늘은 1년 단위 수급 사이클로 장기 예측 활용도가 가장 높은 작물 중 하나입니다."],
        },
    },
    "potato": {
        "headline": "감자 — 봄·여름 출하 집중, 저장물량이 가격 안정 역할",
        "reasons": {
            "short": [
                {"label": "시즌 내 일일 출하량", "direction": "neutral", "direction_label": "→ 단기 수급",
                 "description": "제주 봄감자(4~5월)·내륙 여름감자(6~7월) 출하 피크 시 일일 입하량이 단기 가격을 결정합니다."},
                {"label": "기상 생육 영향", "direction": "up", "direction_label": "↑ 단기 피해 가능",
                 "description": "생육기 냉해·침수는 출하 지연과 규격 외 물량 증가로 단기 상품성 저하와 가격 왜곡을 유발합니다."},
            ],
            "medium": [
                {"label": "여름·가을 단경기", "direction": "up", "direction_label": "↑ 계절 상승",
                 "description": "봄감자 출하 종료(8월) 후 가을·겨울 저장 물량에 의존하는 시기, 저장 재고 수준에 따라 가격이 오릅니다."},
                {"label": "저장 유통 안정성", "direction": "down", "direction_label": "↓ 공급 완충",
                 "description": "CA 저장 시설 확충으로 2~3개월 전진 공급이 가능해 과거 대비 단경기 가격 급등폭이 감소 추세입니다."},
            ],
            "long": [
                {"label": "국내 소비 트렌드", "direction": "neutral", "direction_label": "→ 수요 안정",
                 "description": "가공용(냉동감자·스낵) 수요 증가와 가정 소비 정체가 복합적으로 작용해 전체 수요는 비교적 안정적입니다."},
                {"label": "농가 재배 의향", "direction": "neutral", "direction_label": "→ 공급 조정",
                 "description": "전년 가격 수준이 다음 시즌 파종 면적을 결정하며, 3개월 이후 공급 방향을 예측하는 장기 지표입니다."},
            ],
        },
        "notes": {
            "short": ["감자는 계절 내 단기 예측 시 산지별 출하 일정을 파악하는 것이 중요합니다."],
            "medium": ["저장 물량과 출하 속도가 2개월 가격 전망의 핵심입니다."],
            "long": ["감자는 저장성이 높아 장기 가격 안정성이 다른 채소류보다 높은 편입니다."],
        },
    },
    "sweet_potato": {
        "headline": "고구마 — 저장성 높고 가공 수요 증가, 가격 비교적 안정",
        "reasons": {
            "short": [
                {"label": "산지 출하 속도", "direction": "neutral", "direction_label": "→ 단기 공급 조절",
                 "description": "주산지(경기 여주·충남 해남)의 일일 출하량이 도매시장 단기 가격을 결정합니다."},
                {"label": "소비 계절성", "direction": "up", "direction_label": "↑ 겨울 수요",
                 "description": "추위가 시작되는 11월~2월 간식용 구운 고구마 소비가 증가해 단기 가격 상승 요인이 됩니다."},
            ],
            "medium": [
                {"label": "저장 출하 전략", "direction": "neutral", "direction_label": "→ 출하 시기 조절",
                 "description": "농가와 농협이 저장 물량 출하 시점을 조절하여 2개월 단위 공급량이 가격에 영향을 줍니다."},
                {"label": "가공용 수요", "direction": "down", "direction_label": "↓ 소비 확대",
                 "description": "고구마 라면·스낵·음료 등 가공식품 원료 수요 증가가 단가를 지지하여 가격 하락폭을 제한합니다."},
            ],
            "long": [
                {"label": "건강식품 수요 트렌드", "direction": "up", "direction_label": "↑ 장기 수요 증가",
                 "description": "혈당 지수가 낮고 식이섬유가 풍부한 건강식품으로 인식되면서 연간 소비량이 증가 추세입니다."},
                {"label": "재배 면적 조정", "direction": "neutral", "direction_label": "→ 공급 균형",
                 "description": "전년 가격과 수익성에 따라 다음 시즌 재배 면적이 결정되어 장기 공급을 조정합니다."},
            ],
        },
        "notes": {
            "short": ["고구마는 겨울철 소비 증가로 11월~2월 단기 강세 패턴이 반복됩니다."],
            "medium": ["저장 물량 출하 시점 조절로 2개월 단위 공급이 비교적 안정적으로 유지됩니다."],
            "long": ["건강식 트렌드와 가공 수요 증가로 장기 수요 기반이 강화되고 있습니다."],
        },
    },
    "pepper": {
        "headline": "건고추 — 연산 작황·중국 수입이 연간 가격 수준 결정",
        "reasons": {
            "short": [
                {"label": "현재 재고 수준", "direction": "neutral", "direction_label": "→ 단기 공급 현황",
                 "description": "작년 생산된 저장 건고추 재고 소진 속도가 단기 가격 방향을 결정합니다. 재고 부족 시 즉시 상승합니다."},
                {"label": "김치 제조업체 구매", "direction": "up", "direction_label": "↑ 구매 집중",
                 "description": "김치 제조업체와 김장 시즌 직전 대형 구매가 단기 가격을 빠르게 밀어 올릴 수 있습니다."},
            ],
            "medium": [
                {"label": "수확기 작황 전망", "direction": "neutral", "direction_label": "→ 2개월 핵심 변수",
                 "description": "8~9월 수확기 건고추 작황(착과 수·건조 중량)이 확정되면서 2개월 후 공급량이 결정됩니다."},
                {"label": "중국산 수입 타이밍", "direction": "down", "direction_label": "↓ 공급 보완",
                 "description": "국내 가격이 오르면 중국산 건고추 수입이 2~3개월 내 본격화되어 가격 상승폭을 제한합니다."},
            ],
            "long": [
                {"label": "연산 재고율", "direction": "neutral", "direction_label": "→ 장기 공급 기준",
                 "description": "수확 후 저장 물량이 다음 해 수확 전까지 연중 공급을 책임집니다. 재고 부족 시 연중 강세입니다."},
                {"label": "고추 재배 면적 트렌드", "direction": "up", "direction_label": "↑ 장기 공급 감소",
                 "description": "농촌 고령화와 노동력 부족으로 고추 재배 면적이 지속 감소 추세여서 장기 공급 감소 압력이 있습니다."},
            ],
        },
        "notes": {
            "short": ["건고추는 단기 재고 수준과 김치 업체 구매 동향이 가장 중요한 지표입니다."],
            "medium": ["8~9월 수확기 현장 작황 조사 결과가 2~3개월 가격 전망을 결정합니다."],
            "long": ["농촌 인구 감소에 따른 재배 면적 축소가 장기 가격 상승의 구조적 요인입니다."],
        },
    },
    "fresh_pepper": {
        "headline": "풋고추 — 시설 연중 생산, 여름 노지와 단가 경쟁",
        "reasons": {
            "short": [
                {"label": "일일 출하 물량", "direction": "neutral", "direction_label": "→ 즉각 반응",
                 "description": "풋고추는 저장성이 낮아 당일 출하량이 바로 가격에 반영됩니다. 일일 입하 감소가 즉시 상승 신호입니다."},
                {"label": "기상 생육 속도", "direction": "up", "direction_label": "↑ 날씨 민감",
                 "description": "흐린 날씨·저온 시 생육이 느려져 출하량이 줄고 가격이 오릅니다. 반대로 맑은 고온이면 단기 하락합니다."},
            ],
            "medium": [
                {"label": "여름 노지 대규모 출하", "direction": "down", "direction_label": "↓ 공급 급증",
                 "description": "7~8월 노지 풋고추 대량 출하 시 가격이 큰 폭으로 하락합니다. 시설 재배 농가와 단가 경쟁이 심화됩니다."},
                {"label": "시설 재배 비중", "direction": "down", "direction_label": "↓ 연중 공급 안정",
                 "description": "온실 시설 재배 비중 증가로 계절 가격 변동폭이 과거 대비 줄어드는 추세입니다."},
            ],
            "long": [
                {"label": "매운 음식 소비 트렌드", "direction": "up", "direction_label": "↑ 수요 지속",
                 "description": "국내 매운 음식 선호 증가와 외식 소비 확대로 풋고추 장기 수요는 안정적으로 유지됩니다."},
                {"label": "재배 기술 발전", "direction": "down", "direction_label": "↓ 생산성 향상",
                 "description": "스마트팜·LED 재배 기술 발전으로 단위 면적당 생산량이 증가해 장기적으로 공급이 늘어날 전망입니다."},
            ],
        },
        "notes": {
            "short": ["풋고추는 저장성이 없어 단기 수급이 가격을 직접 결정합니다. 일일 입하량 확인이 가장 중요합니다."],
            "medium": ["여름 노지 출하(7~8월)는 풋고추 가격의 연간 최저점 구간입니다."],
            "long": ["시설 재배 확대로 장기적인 가격 안정화가 진행 중이나 에너지 비용 변화에 영향을 받습니다."],
        },
    },
    "tomato": {
        "headline": "토마토 — 시설 연중 출하, 에너지 비용·기온이 계절 가격 결정",
        "reasons": {
            "short": [
                {"label": "일일 출하 속도", "direction": "neutral", "direction_label": "→ 단기 공급 현황",
                 "description": "토마토는 저장성이 낮아 일별 출하 물량이 즉각 가격에 반영됩니다. 과잉 출하 시 당일 가격이 급락할 수 있습니다."},
                {"label": "기온·일조 영향", "direction": "up", "direction_label": "↑ 날씨 민감",
                 "description": "저온·흐린 날씨는 착과율을 낮추고 출하를 지연시켜 단기 공급 감소와 가격 상승으로 이어집니다."},
            ],
            "medium": [
                {"label": "여름 출하 집중", "direction": "down", "direction_label": "↓ 공급 과잉",
                 "description": "6~8월 노지·반시설 토마토 대량 출하로 가격이 하락하며, 2개월 예측 시 이 계절 패턴을 반영합니다."},
                {"label": "시설 에너지 비용", "direction": "up", "direction_label": "↑ 겨울 가격 상승",
                 "description": "가을~겨울 시설 난방비 증가가 생산 원가를 높여 10~2월 가격 상승으로 이어지는 패턴이 있습니다."},
            ],
            "long": [
                {"label": "수요 다변화", "direction": "up", "direction_label": "↑ 수요 증가",
                 "description": "방울토마토·대추방울 등 프리미엄 품종 수요 증가가 평균 단가를 끌어올리는 장기 트렌드입니다."},
                {"label": "스마트팜 생산성", "direction": "down", "direction_label": "↓ 공급 효율화",
                 "description": "스마트팜 토마토 단수 향상으로 면적당 생산량이 증가해 장기 공급 효율이 올라가고 있습니다."},
            ],
        },
        "notes": {
            "short": ["토마토 단기 가격은 당일 경매 결과와 일조 시간이 가장 빠른 선행 지표입니다."],
            "medium": ["겨울(10월~2월) 시설 가온 비용이 오르는 시기는 중기 가격 상승 구간입니다."],
            "long": ["프리미엄 품종 다양화와 스마트팜 확대가 장기 시장 구조를 바꾸고 있습니다."],
        },
    },
    "cucumber": {
        "headline": "오이 — 여름 노지 대량 출하 vs 겨울 시설 단가 경쟁",
        "reasons": {
            "short": [
                {"label": "일별 경락가 변동", "direction": "neutral", "direction_label": "→ 즉각 반응",
                 "description": "오이는 저장성이 거의 없어 당일 경락가가 수급을 그대로 반영합니다. 출하 집중 시 단기 급락이 발생합니다."},
                {"label": "폭염·냉해 반응", "direction": "up", "direction_label": "↑ 날씨 민감",
                 "description": "여름 고온 스트레스나 겨울 한파 시 생육 장해로 출하가 줄어 단기 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "여름 노지 출하 규모", "direction": "down", "direction_label": "↓ 공급 급증",
                 "description": "7~8월 노지 오이 대량 출하 시 가격이 연중 최저 수준으로 떨어지는 계절 패턴이 있습니다."},
                {"label": "가을 시설 전환", "direction": "up", "direction_label": "↑ 공급 감소",
                 "description": "노지 생산 종료 후 시설 재배로 전환하는 과도기에 공급이 줄어 가격이 반등합니다."},
            ],
            "long": [
                {"label": "소비 채널 다변화", "direction": "up", "direction_label": "↑ 수요 지지",
                 "description": "샐러드·건강식 트렌드로 오이 소비 채널이 외식 중심에서 가정 소비로 확대되는 장기 흐름이 있습니다."},
                {"label": "시설 난방비 구조", "direction": "up", "direction_label": "↑ 겨울 원가 상승",
                 "description": "시설 재배 비중이 높아 에너지 가격 상승이 겨울 오이 생산 원가와 장기 가격에 영향을 줍니다."},
            ],
        },
        "notes": {
            "short": ["오이는 단기 예측에서 일별 도매시장 경락가가 가장 정확한 선행 지표입니다."],
            "medium": ["여름 노지 출하 피크(7~8월)는 연간 최저가 구간이며 이후 시설 전환 시 가격이 오릅니다."],
            "long": ["에너지 비용과 스마트팜 생산성이 장기 가격 구조를 결정하는 핵심 변수입니다."],
        },
    },
    "zucchini": {
        "headline": "애호박 — 연중 시설 생산, 계절별 수요-공급 균형이 핵심",
        "reasons": {
            "short": [
                {"label": "일일 출하 수급", "direction": "neutral", "direction_label": "→ 단기 결정",
                 "description": "애호박은 저장성이 없어 당일 출하량이 바로 가격에 반영됩니다."},
                {"label": "기온 생육 속도", "direction": "neutral", "direction_label": "→ 날씨 영향",
                 "description": "고온기에는 생육이 빨라 공급이 늘고, 저온기에는 늦어져 공급이 줄면서 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "여름 공급 과잉", "direction": "down", "direction_label": "↓ 계절 하락",
                 "description": "여름(7~8월) 노지·시설 애호박 동시 출하로 공급이 늘어 가격이 내려가는 계절 패턴이 있습니다."},
                {"label": "가을 수요 회복", "direction": "up", "direction_label": "↑ 수요 회복",
                 "description": "여름 이후 찌개·나물 소비 증가와 함께 수요가 회복되면서 2개월 후 가격이 반등합니다."},
            ],
            "long": [
                {"label": "외식 소비 연동", "direction": "neutral", "direction_label": "→ 경기 연동",
                 "description": "애호박 소비의 상당 부분이 외식 업계에서 이루어져 경기 상황과 외식 트렌드에 장기 가격이 영향을 받습니다."},
            ],
        },
        "notes": {
            "short": ["단기 예측에서 일별 입하량과 도매 경락가 데이터가 가장 신뢰성 있는 지표입니다."],
            "medium": ["여름 공급 과잉 후 가을 반등이 연간 반복되는 계절 패턴입니다."],
            "long": ["외식 경기와 연동되어 장기 가격 전망 시 경기 지표도 참고해야 합니다."],
        },
    },
    "carrot": {
        "headline": "당근 — 제주 겨울당근·수입당근이 연중 공급의 양대 축",
        "reasons": {
            "short": [
                {"label": "수입 물량 동향", "direction": "down", "direction_label": "↓ 수입 공급 효과",
                 "description": "중국·호주산 당근 수입 물량이 단기 국내 공급을 조절하며 가격 상한선 역할을 합니다."},
                {"label": "제주 출하 일정", "direction": "neutral", "direction_label": "→ 출하 타이밍",
                 "description": "제주 겨울당근(12~4월) 출하 시작 및 종료 타이밍이 단기 공급 변동의 주요 변수입니다."},
            ],
            "medium": [
                {"label": "봄 국내 출하 공백", "direction": "up", "direction_label": "↑ 공급 감소",
                 "description": "제주 겨울당근 출하 종료(4~5월) 후 여름 당근 출하 전까지 공급 공백이 생겨 가격이 오릅니다."},
                {"label": "수입 계약 물량", "direction": "down", "direction_label": "↓ 공급 보완",
                 "description": "국내 가격 상승 시 수입 당근 계약이 늘어나 2~3개월 내 물량이 들어와 가격을 안정시킵니다."},
            ],
            "long": [
                {"label": "재배 면적 통계", "direction": "neutral", "direction_label": "→ 장기 공급",
                 "description": "국내 당근 재배 면적과 단수가 장기 공급량을 결정하며 수입 대체 수준을 결정합니다."},
                {"label": "가공·즙 수요 증가", "direction": "up", "direction_label": "↑ 수요 확대",
                 "description": "당근 착즙·분말·가공식품 원료 수요 증가가 장기 가격을 지지합니다."},
            ],
        },
        "notes": {
            "short": ["제주 겨울당근 출하 일정과 수입 물량 통관 현황을 함께 모니터링하는 것이 중요합니다."],
            "medium": ["4~5월 제주 출하 종료 후 공급 공백기가 연간 최고가 구간이 되는 경향이 있습니다."],
            "long": ["수입 의존도가 높은 작물로, 중국·호주 현지 작황과 환율이 장기 가격에 영향을 줍니다."],
        },
    },
    "spinach": {
        "headline": "시금치 — 저장 불가, 단기 수급이 가격 전부",
        "reasons": {
            "short": [
                {"label": "당일 출하 물량", "direction": "neutral", "direction_label": "→ 즉각 결정",
                 "description": "시금치는 저장이 거의 불가능해 당일 출하량이 가격을 결정합니다. 공급 감소 시 당일 가격이 50~100% 오를 수 있습니다."},
                {"label": "기온 생육 속도", "direction": "up", "direction_label": "↑ 겨울 수요·공급 동시 영향",
                 "description": "저온기(11~2월)에는 생육이 느려 공급이 줄고 동시에 소비가 늘어 가격이 빠르게 오릅니다."},
            ],
            "medium": [
                {"label": "계절 출하 패턴", "direction": "neutral", "direction_label": "→ 계절 구조",
                 "description": "봄(3~5월)과 겨울(11~1월)이 시금치 성수기이며 여름은 열에 약해 공급이 줄고 가격이 오르는 계절입니다."},
                {"label": "여름 시설 재배", "direction": "down", "direction_label": "↓ 공급 보완",
                 "description": "여름 단경기 대응을 위한 냉방 시설 재배가 늘어나 중기 가격 안정화에 기여하고 있습니다."},
            ],
            "long": [
                {"label": "건강식 수요 증가", "direction": "up", "direction_label": "↑ 장기 수요",
                 "description": "철분·비타민 함량 등 건강 기능이 부각되면서 샐러드·냉동 시금치 수요가 증가 추세입니다."},
            ],
        },
        "notes": {
            "short": ["시금치는 단기 예측이 가장 중요한 작물 중 하나입니다. 당일 경매 결과가 모든 것입니다."],
            "medium": ["여름 단경기(7~8월)는 시금치 가격이 가장 불안정한 시기입니다."],
            "long": ["시금치는 저장성이 없어 장기 예측 활용도는 다른 저장 작물보다 낮습니다."],
        },
    },
    "lettuce": {
        "headline": "상추 — 연중 시설 생산, 삼겹살 소비와 동조화",
        "reasons": {
            "short": [
                {"label": "삼겹살 소비 연동", "direction": "up", "direction_label": "↑ 외식 수요",
                 "description": "주말 외식·삼겹살 시즌에는 상추 수요가 일시 급증해 단기 가격이 오를 수 있습니다."},
                {"label": "기온 생육 영향", "direction": "neutral", "direction_label": "→ 날씨 연동",
                 "description": "적정 기온(15~25°C)에서 생육이 가장 빠르며, 고온기나 한파 시 생육 지연으로 출하가 줄어듭니다."},
            ],
            "medium": [
                {"label": "여름 볼트 현상", "direction": "up", "direction_label": "↑ 여름 공급 감소",
                 "description": "여름 고온 시 상추 꽃대가 올라오는 볼트(추대) 현상으로 상품성이 떨어지고 공급이 줄어 가격이 오릅니다."},
                {"label": "시설 재배 비중", "direction": "down", "direction_label": "↓ 공급 안정",
                 "description": "대부분 시설 재배로 연중 안정 공급이 가능하나, 에너지 비용 상승 시기에 생산 원가가 올라 가격에 반영됩니다."},
            ],
            "long": [
                {"label": "쌈 채소 소비 문화", "direction": "up", "direction_label": "↑ 수요 안정",
                 "description": "한국 외식 문화의 쌈 채소 소비 습관이 지속되어 상추 수요 기반이 장기적으로 안정적입니다."},
                {"label": "스마트팜 확대", "direction": "down", "direction_label": "↓ 생산성 향상",
                 "description": "LED 식물공장·수경재배 상추 생산이 늘어나 장기적으로 공급 효율화와 가격 안정화가 기대됩니다."},
            ],
        },
        "notes": {
            "short": ["상추는 외식 업계 삼겹살 시즌과 연동되는 단기 수요 패턴이 있습니다."],
            "medium": ["여름 볼트 현상으로 7~8월이 연중 가장 비싼 시기입니다."],
            "long": ["LED 스마트팜 확대가 장기적으로 상추 가격 안정에 기여할 것으로 전망됩니다."],
        },
    },
    "perilla": {
        "headline": "깻잎 — 시설 연중 생산, 프리미엄 쌈 채소 수요 안정",
        "reasons": {
            "short": [
                {"label": "일일 출하량", "direction": "neutral", "direction_label": "→ 단기 수급",
                 "description": "깻잎은 당일 출하량이 바로 가격에 반영됩니다. 출하 감소 시 단기 가격이 빠르게 오릅니다."},
                {"label": "기온·일조 영향", "direction": "up", "direction_label": "↑ 날씨 민감",
                 "description": "저온·일조 부족 시 생육이 늦어져 출하량이 줄고 단기 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "겨울 난방비 상승", "direction": "up", "direction_label": "↑ 겨울 원가 부담",
                 "description": "시설 가온 비용이 증가하는 11~2월에 생산 원가 상승이 중기 가격 지지 요인이 됩니다."},
                {"label": "외식 수요 계절성", "direction": "neutral", "direction_label": "→ 외식 연동",
                 "description": "구이 음식 외식 성수기(봄·가을)에 쌈 채소 수요가 집중되어 2개월 가격 방향에 영향을 줍니다."},
            ],
            "long": [
                {"label": "건강 기능 인식 확대", "direction": "up", "direction_label": "↑ 수요 증가",
                 "description": "항산화·항염 등 건강 기능성 인식 확대로 깻잎 소비가 점차 늘어나는 장기 트렌드가 있습니다."},
            ],
        },
        "notes": {
            "short": ["깻잎 단기 가격은 일조 시간과 당일 출하량이 핵심 변수입니다."],
            "medium": ["겨울 시설 난방비 구간(11~2월)이 연중 가격이 가장 높은 시기입니다."],
            "long": ["건강식 트렌드와 외식 수요 확대로 장기 가격 지지 기반이 강화되고 있습니다."],
        },
    },
    "watermelon": {
        "headline": "수박 — 여름 성수기 집중 출하, 냉해·우박이 최대 리스크",
        "reasons": {
            "short": [
                {"label": "성수기 출하 집중", "direction": "down", "direction_label": "↓ 공급 최대",
                 "description": "6~8월 여름 수박 출하 피크 시 공급 과잉으로 가격이 낮아집니다. 날씨가 좋을수록 출하 집중도가 높아집니다."},
                {"label": "우박·집중호우 피해", "direction": "up", "direction_label": "↑ 단기 급등",
                 "description": "생육기 우박이나 침수 피해가 발생하면 상품성 손상으로 단기 공급이 줄어 가격이 빠르게 오릅니다."},
            ],
            "medium": [
                {"label": "추석 선물세트 수요", "direction": "up", "direction_label": "↑ 명절 수요",
                 "description": "추석 선물세트용 고품질 수박 수요가 8~9월 중기 가격을 지지합니다."},
                {"label": "후기 출하 물량", "direction": "down", "direction_label": "↓ 공급 지속",
                 "description": "강원 고랭지 수박(8~9월)이 후기 출하되면서 가격 하락 압력을 유지합니다."},
            ],
            "long": [
                {"label": "비수기 가격 강세", "direction": "up", "direction_label": "↑ 겨울 희소성",
                 "description": "겨울 시설 수박 생산은 제한적이어서 11~4월 가격이 여름 대비 크게 높아지는 패턴이 있습니다."},
                {"label": "소과 품종 수요 증가", "direction": "up", "direction_label": "↑ 소비 패턴 변화",
                 "description": "1~2인 가구 증가로 소과(미니)수박 수요가 늘어 장기 평균 단가를 높이는 구조적 변화가 있습니다."},
            ],
        },
        "notes": {
            "short": ["여름 성수기 기상(폭염·우박·집중호우)이 수박 단기 가격의 최대 변수입니다."],
            "medium": ["추석 명절 선물 수요와 고랭지 후기 출하 물량이 2개월 가격을 결정합니다."],
            "long": ["소과 수박 수요 증가가 장기 시장 구조를 바꾸는 중요한 트렌드입니다."],
        },
    },
    "chamoe": {
        "headline": "참외 — 경북 성주 집중 산지, 여름 성수기 가격 구조",
        "reasons": {
            "short": [
                {"label": "성주 산지 출하량", "direction": "neutral", "direction_label": "→ 단기 수급",
                 "description": "참외 생산의 70%를 차지하는 경북 성주의 일일 출하량이 단기 가격을 거의 결정합니다."},
                {"label": "고온 피해", "direction": "up", "direction_label": "↑ 열과 피해",
                 "description": "여름 극단적 고온(35°C 이상) 시 열과·착색 불량이 증가해 상품과 출하가 줄고 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "성수기 수요 집중", "direction": "up", "direction_label": "↑ 여름 소비 증가",
                 "description": "6~8월 여름 과일 소비 성수기에 참외 수요가 집중되어 출하 증가에도 가격이 지지됩니다."},
                {"label": "경쟁 과일 출하", "direction": "down", "direction_label": "↓ 대체 소비",
                 "description": "같은 시기 수박·복숭아 등 경쟁 과일 대량 출하 시 참외 소비가 분산되어 가격 상승폭이 제한됩니다."},
            ],
            "long": [
                {"label": "비수기 가격 강세", "direction": "up", "direction_label": "↑ 겨울 희소성",
                 "description": "겨울·봄 시설 참외는 생산량이 적어 단가가 여름 대비 크게 높아 장기 가격 평균을 끌어올립니다."},
                {"label": "품종 고급화", "direction": "up", "direction_label": "↑ 단가 상승",
                 "description": "프리미엄 품종 개발과 선물세트 시장 확대로 장기 평균 단가가 오르는 추세입니다."},
            ],
        },
        "notes": {
            "short": ["참외는 성주 산지 집중도가 매우 높아 해당 지역 기상이 가장 중요한 단기 변수입니다."],
            "medium": ["여름 과일 시장 경쟁(수박·복숭아)이 2개월 참외 가격 방향에 영향을 줍니다."],
            "long": ["겨울·봄 시설 참외 가격 강세가 연간 평균 단가를 지지합니다."],
        },
    },
    "sesame": {
        "headline": "참깨 — 수입 의존도 높아 환율·국제 시세가 핵심 변수",
        "reasons": {
            "short": [
                {"label": "수입 물량 통관", "direction": "down", "direction_label": "↓ 수입 공급",
                 "description": "참깨 국내 자급률이 낮아 수입 물량 통관 일정이 단기 국내 가격에 영향을 줍니다."},
                {"label": "성수기 수요", "direction": "up", "direction_label": "↑ 명절 수요",
                 "description": "추석·설 명절 시즌에 나물·참기름 수요가 집중되어 단기 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "국제 시세 변동", "direction": "neutral", "direction_label": "→ 수입가 연동",
                 "description": "인도·수단·나이지리아 등 수입 원산지의 국제 참깨 가격이 2~3개월 후 국내 도매가에 반영됩니다."},
                {"label": "환율 영향", "direction": "neutral", "direction_label": "→ 환율 민감",
                 "description": "원/달러 환율 상승 시 수입 원가가 오르고 국내 가격 상승 압력으로 이어집니다."},
            ],
            "long": [
                {"label": "국내 생산 감소 추세", "direction": "up", "direction_label": "↑ 장기 공급 감소",
                 "description": "농촌 고령화로 참깨 국내 재배 면적이 지속 감소하여 장기 수입 의존도가 높아지는 구조적 문제가 있습니다."},
                {"label": "건강식 수요 증가", "direction": "up", "direction_label": "↑ 장기 수요",
                 "description": "참기름·들기름 등 건강 식용유 수요 증가가 장기 참깨 가격을 지지합니다."},
            ],
        },
        "notes": {
            "short": ["명절(추석·설) 전후 단기 수요 급증 시즌에 주의가 필요합니다."],
            "medium": ["국제 참깨 시세와 원/달러 환율이 2개월 국내 가격 전망의 핵심 변수입니다."],
            "long": ["수입 의존도가 80% 이상으로 장기 전망 시 국제 시세·환율·농업 정책을 종합 고려해야 합니다."],
        },
    },
    "apple": {
        "headline": "사과 — 냉해·우박·저장 재고가 연간 가격의 3대 변수",
        "reasons": {
            "short": [
                {"label": "저장 출하 속도", "direction": "neutral", "direction_label": "→ 단기 공급",
                 "description": "CA 저장 사과 출하 속도가 단기 공급량을 결정합니다. 출하 감소 시 즉시 가격이 오릅니다."},
                {"label": "신구과 교체 시기", "direction": "up", "direction_label": "↑ 7~8월 공급 공백",
                 "description": "전년산 저장 사과 소진과 당해 수확(10월) 사이인 7~8월에 공급 공백이 생겨 단기 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "수확기 작황 전망", "direction": "neutral", "direction_label": "→ 2개월 핵심",
                 "description": "9~10월 수확기를 앞두고 착과 수·비대 상황이 출하 예상 물량을 결정해 2개월 후 가격 방향을 제시합니다."},
                {"label": "명절 선물 수요", "direction": "up", "direction_label": "↑ 추석 수요",
                 "description": "추석(9~10월) 선물세트 사과 수요 집중으로 수확 직전~직후 가격이 강세를 보입니다."},
            ],
            "long": [
                {"label": "해거리 생산 패턴", "direction": "neutral", "direction_label": "→ 격년 변동",
                 "description": "사과는 격년(해거리)으로 풍작과 흉작이 반복되는 경향이 있어 전년 작황 확인이 장기 전망의 출발점입니다."},
                {"label": "기후 변화 영향", "direction": "up", "direction_label": "↑ 장기 공급 리스크",
                 "description": "재배 적지가 북상하면서 기존 경북 주산지의 착과 안정성이 낮아지고 있어 장기 공급 불안 요인이 됩니다."},
            ],
        },
        "notes": {
            "short": ["사과는 신구과 교체 시기(7~8월)가 연간 최고가 구간입니다."],
            "medium": ["추석 명절 수요와 수확기 작황이 동시에 결정되는 9~10월이 가장 변동성이 큰 시기입니다."],
            "long": ["해거리 패턴과 기후 변화가 장기 예측의 핵심 변수입니다. 전년 작황을 반드시 확인하세요."],
        },
    },
    "pear": {
        "headline": "배 — 추석 선물 수요·수출이 가격 방향 결정",
        "reasons": {
            "short": [
                {"label": "저장 출하 동향", "direction": "neutral", "direction_label": "→ 단기 공급",
                 "description": "신고배 CA 저장 물량의 출하 속도가 단기 공급을 결정하며, 출하 지연 시 가격이 오릅니다."},
                {"label": "추석 명절 수요", "direction": "up", "direction_label": "↑ 명절 집중",
                 "description": "추석 선물세트 배 수요가 수확 직후(9~10월) 가격을 강하게 지지합니다."},
            ],
            "medium": [
                {"label": "수출 물량", "direction": "up", "direction_label": "↑ 수출 수요",
                 "description": "미국·캐나다 등 대미 수출 물량 증가 시 국내 고품질 배 공급이 줄어 국내 가격이 오릅니다."},
                {"label": "수확기 작황", "direction": "neutral", "direction_label": "→ 공급량 결정",
                 "description": "9~10월 수확기 배 단수와 규격과 비율이 2개월 후 공급량과 가격 방향을 결정합니다."},
            ],
            "long": [
                {"label": "재배 면적 감소", "direction": "up", "direction_label": "↑ 장기 공급 감소",
                 "description": "농가 고령화와 배 재배 포기 증가로 국내 재배 면적이 지속 감소 추세여서 장기 가격 상승 압력이 있습니다."},
                {"label": "수입 배 경쟁", "direction": "down", "direction_label": "↓ 수입 대체",
                 "description": "중국산 배 수입이 늘어나면서 국내산 중저가 배 시장의 가격 상승을 제한합니다."},
            ],
        },
        "notes": {
            "short": ["추석 전후(9~10월) 단기 수요 집중이 배 가격의 연간 최고점을 만듭니다."],
            "medium": ["수출 계약 물량과 추석 선물 수요가 동시에 결정되는 8~9월이 핵심 관찰 시기입니다."],
            "long": ["재배 면적 감소 추세가 지속되면 장기적으로 국내산 배 공급이 줄어 가격 강세가 예상됩니다."],
        },
    },
    "grape": {
        "headline": "포도 — 캠벨·샤인머스캣 이원화, 고가 품종이 평균 단가 견인",
        "reasons": {
            "short": [
                {"label": "산지 출하 집중도", "direction": "down", "direction_label": "↓ 성수기 공급",
                 "description": "8~9월 포도 성수기 출하 집중으로 캠벨 등 일반 품종 가격이 낮아지는 계절 패턴이 있습니다."},
                {"label": "우박·비 피해", "direction": "up", "direction_label": "↑ 단기 리스크",
                 "description": "수확기 우박·집중호우는 포도 알 파열과 당도 저하로 상품성을 크게 떨어뜨려 가격이 급등합니다."},
            ],
            "medium": [
                {"label": "샤인머스캣 출하", "direction": "neutral", "direction_label": "→ 고가 품종 출하",
                 "description": "9~10월 샤인머스캣 출하 집중 시 고가 시장 형성으로 포도 전체 평균 단가에 영향을 줍니다."},
                {"label": "추석 선물 수요", "direction": "up", "direction_label": "↑ 명절 수요",
                 "description": "추석 선물세트용 고품질 포도 수요가 8~9월 중기 가격을 지지하는 요인입니다."},
            ],
            "long": [
                {"label": "샤인머스캣 재배 확대", "direction": "down", "direction_label": "↓ 공급 증가",
                 "description": "샤인머스캣 재배 면적 급증으로 향후 공급 과잉이 우려되어 장기 단가 하락 압력이 커지고 있습니다."},
                {"label": "수입 포도 경쟁", "direction": "down", "direction_label": "↓ 수입 대체",
                 "description": "칠레산 포도 수입이 비수기(12~4월)에 집중되어 국내산과 시즌 충돌은 적지만 소비자 인식에 영향을 줍니다."},
            ],
        },
        "notes": {
            "short": ["수확기(8~9월) 기상이 포도 단기 가격의 핵심 변수입니다."],
            "medium": ["샤인머스캣 출하 증가로 포도 시장이 이원화되는 중기 트렌드를 주목하세요."],
            "long": ["샤인머스캣 재배 과잉으로 인한 장기 단가 조정 가능성을 반드시 고려해야 합니다."],
        },
    },
    "strawberry": {
        "headline": "딸기 — 겨울 시설 성수기, 에너지 비용·수출이 핵심 변수",
        "reasons": {
            "short": [
                {"label": "일별 출하량", "direction": "neutral", "direction_label": "→ 즉각 반응",
                 "description": "딸기는 저장성이 매우 낮아 당일 출하량이 즉시 가격에 반영됩니다."},
                {"label": "겨울 기온", "direction": "up", "direction_label": "↑ 한파 시 공급 감소",
                 "description": "성수기인 12~2월 한파가 강할수록 생육이 느려져 출하가 감소하고 단기 가격이 오릅니다."},
            ],
            "medium": [
                {"label": "일본 수출 물량", "direction": "up", "direction_label": "↑ 수출 집중",
                 "description": "일본 수출 딸기 물량이 늘어나면 국내 고품질 딸기 공급이 줄어 2개월 중기 가격을 밀어 올립니다."},
                {"label": "봄 출하 증가", "direction": "down", "direction_label": "↓ 공급 회복",
                 "description": "3~4월 봄 기온 상승으로 출하량이 늘어나고 가격이 하락하는 계절 패턴이 있습니다."},
            ],
            "long": [
                {"label": "비수기 가격 강세", "direction": "up", "direction_label": "↑ 여름 희소성",
                 "description": "6~10월 딸기 비수기에는 공급이 매우 적어 프리미엄 가격이 형성됩니다."},
                {"label": "수출 시장 다변화", "direction": "up", "direction_label": "↑ 수출 수요 증가",
                 "description": "일본 외 동남아·중동으로 수출 시장이 확대되면서 장기적으로 수출 물량 증가가 국내 공급을 줄이는 구조가 강화됩니다."},
            ],
        },
        "notes": {
            "short": ["딸기는 단기 저장이 어려워 일일 경매 결과가 가격 예측의 핵심 지표입니다."],
            "medium": ["일본 수출 계약 물량이 2~3개월 국내 공급량에 직접 영향을 줍니다."],
            "long": ["수출 시장 확대와 에너지 비용이 장기 딸기 가격 구조를 결정하는 두 가지 핵심 변수입니다."],
        },
    },
}

_CROP_STATIC_DEFAULT = {
    "reasons": {
        "short": [
            {"label": "단기 수급 균형", "direction": "neutral", "direction_label": "→ 실시간 파악",
             "description": "도매시장 일일 입하량과 경락가를 기반으로 1~3주 수급 균형을 평가합니다."},
            {"label": "기상 충격", "direction": "up", "direction_label": "↑ 단기 리스크",
             "description": "주산지 폭염·한파·집중호우 발생 시 생육 피해로 1~2주 내 출하량이 줄어 가격이 급등할 수 있습니다."},
        ],
        "medium": [
            {"label": "계절 수급 패턴", "direction": "neutral", "direction_label": "→ 계절 변동",
             "description": "해당 작물의 출하 성수기·단경기 패턴을 반영하여 2개월 가격 방향을 분석합니다."},
            {"label": "저장·수입 동향", "direction": "neutral", "direction_label": "→ 공급 완충",
             "description": "저장 물량 출하 속도와 수입 동향이 중기 공급을 조절하여 가격 변동폭을 결정합니다."},
        ],
        "long": [
            {"label": "재배 면적·작황 전망", "direction": "neutral", "direction_label": "→ 장기 공급",
             "description": "당해 파종 면적과 생육 상황이 3개월 후 출하량을 결정하는 장기 지표입니다."},
            {"label": "수요 트렌드", "direction": "neutral", "direction_label": "→ 소비 변화",
             "description": "가공 수요·수출·건강식 트렌드 등 소비 구조 변화가 장기 가격 방향에 영향을 줍니다."},
        ],
    },
    "notes": {
        "short": ["단기 예측은 기상 이변과 산지 출하 동향 모니터링이 핵심입니다."],
        "medium": ["2개월 예측 시 계절 출하 패턴과 저장 재고 현황을 참고하세요."],
        "long": ["장기 예측은 재배 면적·작황 조사 통계와 수요 트렌드를 함께 고려합니다."],
    },
}


@router.get("/{item_code}/forecast/explanation")
async def get_forecast_explanation(
    item_code: str,
    target_date: str = None,
    horizon: int = 14,
    db: AsyncSession = Depends(get_db),
):
    item, fc, base_date = await _load_item_forecast(item_code, target_date, db, horizon=horizon)
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

    phase = _horizon_phase(horizon)
    static = _CROP_STATIC.get(item_code, _CROP_STATIC_DEFAULT)
    static_reasons = static.get("reasons", {})
    if isinstance(static_reasons, dict):
        static_reasons = static_reasons.get(phase, static_reasons.get("short", []))
    static_notes_raw = static.get("notes", {})
    if isinstance(static_notes_raw, dict):
        static_notes = static_notes_raw.get(phase, static_notes_raw.get("short", []))
    else:
        static_notes = static_notes_raw if isinstance(static_notes_raw, list) else []

    phase_label = {"short": "단기(1~3주)", "medium": "중기(1~2개월)", "long": "장기(3개월)"}[phase]

    # fc 없을 때 — 작물별 기간별 정적 설명 반환
    if fc is None:
        return {
            "item_code": item_code,
            "item_name": item.item_name,
            "base_date": str(base_date),
            "headline": static.get("headline", f"{item.item_name} — AI 예측 모델 구조 설명"),
            "horizon": horizon,
            "horizon_phase": phase,
            "horizon_phase_label": phase_label,
            "model": {
                "version": "static",
                "scope": "item",
                "scope_label": f"{phase_label} 예측 근거 설명",
                "confidence": "medium",
                "confidence_label": "참고용",
                "confidence_reason": "파이프라인 실행 전 정적 설명입니다. 실제 AI 예측은 파이프라인 실행 후 업데이트됩니다.",
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
            "reasons": static_reasons,
            "risk_regions": [],
            "data_freshness": {
                "price": _freshness(latest_price_date, base_date, warn_after_days=2),
                "region_signal": _freshness(latest_signal_date, base_date, warn_after_days=1),
                "forecast": {"status": "missing", "status_label": "예측 없음", "latest_date": None},
            },
            "notes": static_notes,
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
    # top_factors 없으면 기간별 정적 데이터로 보완
    if not reasons:
        reasons = static_reasons

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
        "horizon": horizon,
        "horizon_phase": phase,
        "horizon_phase_label": phase_label,
        "reasons": reasons,
        "risk_regions": [_risk_region(region) for region in signal_result.scalars().all()],
        "data_freshness": {
            "price": _freshness(latest_price_date, base_date, warn_after_days=2),
            "region_signal": _freshness(latest_signal_date, base_date, warn_after_days=1),
            "forecast": _freshness(fc.base_date, base_date, warn_after_days=1),
        },
        "notes": static_notes if static_notes else _explanation_notes(model_scope, latest_price_date, latest_signal_date, base_date),
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
