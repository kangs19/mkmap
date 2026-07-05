"""
자연어 설명 엔진 — 기획서 13번

top_factors(피처 중요도) → 한국어 자연어 요약문 생성
"""

# 피처명 → 한국어 레이블 + 방향 해석
FEATURE_LABELS = {
    # 가격
    "price_ma7":          ("단기 가격 추세(7일)", "가격 상승 흐름", "가격 하락 흐름"),
    "price_ma14":         ("중기 가격 추세(14일)", "가격 상승 흐름", "가격 하락 흐름"),
    "price_ma28":         ("장기 가격 추세(28일)", "가격 상승 기조", "가격 하락 기조"),
    "ret_1d":             ("전일 가격 변동", "전일 가격 급등", "전일 가격 급락"),
    "ret_7d":             ("주간 가격 변동률", "주간 가격 상승", "주간 가격 하락"),
    "ret_14d":            ("2주 가격 변동률", "2주 가격 상승", "2주 가격 하락"),
    "volatility_7d":      ("단기 가격 변동성", "단기 변동성 확대", "단기 변동성 축소"),
    "volatility_14d":     ("중기 가격 변동성", "중기 변동성 확대", "중기 변동성 축소"),
    "price_vs_avg_year":  ("평년 가격 대비 편차", "평년보다 높은 가격", "평년보다 낮은 가격"),
    "price_vs_prev_year": ("전년 가격 대비 편차", "전년보다 높은 가격", "전년보다 낮은 가격"),
    "ma7_vs_ma28":        ("단기-장기 이동평균 교차", "단기 가격 강세", "단기 가격 약세"),
    "sin_month":          ("계절 효과(사인)", "계절적 상승 구간", "계절적 하락 구간"),
    "cos_month":          ("계절 효과(코사인)", "계절적 수요 증가", "계절적 수요 감소"),
    # 날씨
    "w_avg_temp":         ("기온", "고온으로 인한 생육 위험", "저온으로 인한 냉해 위험"),
    "w_precipitation":    ("강수량", "과잉 강수로 인한 피해 위험", "가뭄으로 인한 생육 저하"),
    "w_temp_dev":         ("기온 편차(평년 대비)", "이상 고온", "이상 저온"),
    "w_temp_ma7":         ("7일 평균 기온", "지속적 고온", "지속적 저온"),
    "w_precip_ma7":       ("7일 누적 강수량", "집중 호우", "가뭄 지속"),
    "w_heat_alert_7d":    ("7일 폭염 경보 횟수", "폭염 반복으로 작황 위협", "폭염 없음"),
    "w_cold_alert_7d":    ("7일 한파 경보 횟수", "한파로 인한 냉해 위험", "한파 없음"),
    "w_heavy_rain_7d":    ("7일 호우 경보 횟수", "집중 호우로 인한 수확 차질", "강수 안정"),
    # KOSIS 생산통계
    "kosis_area_dev":     ("재배면적 전년 대비", "재배면적 확대(공급 증가 기대)", "재배면적 축소(공급 감소 우려)"),
    "kosis_prod_dev":     ("생산량 전년 대비", "생산량 증가(공급 여유)", "생산량 감소(공급 부족)"),
    "kosis_supply_risk":  ("KOSIS 공급 위험 지수", "공급 부족 신호", "공급 여유 신호"),
    # 거래량
    "mkt_volume_kg":      ("도매시장 거래량", "거래량 증가(수요 활발)", "거래량 감소(수요 위축)"),
    "mkt_volume_ma7":     ("7일 평균 거래량", "거래 증가 추세", "거래 감소 추세"),
    "mkt_volume_ma28":    ("28일 평균 거래량", "장기 거래 증가", "장기 거래 감소"),
    "mkt_volume_vs_avg":  ("거래량 평균 대비 편차", "평균보다 많은 거래(활발)", "평균보다 적은 거래(침체)"),
    "mkt_volume_trend":   ("거래량 7일 추세", "거래 급증", "거래 급감"),
    # 이벤트
    "days_to_kimjang":    ("김장철 접근도", "김장철 임박(수요 급증)", "김장철 후반 또는 비시즌"),
    "is_kimjang_season":  ("김장철 시즌 여부", "김장 성수기(10~12월)", "김장 비시즌"),
    "kimjang_proximity":  ("김장철 근접도", "김장철 30일 이내(수요 급증)", "김장철 멀리"),
    "days_to_chuseok":    ("추석 접근도", "추석 임박(명절 수요)", "추석 이후 또는 비시즌"),
    "chuseok_proximity":  ("추석 근접도", "추석 2주 이내(명절 수요)", "추석 비시즌"),
    "days_to_seol":       ("설 접근도", "설 임박(명절 수요)", "설 비시즌"),
    "seol_proximity":     ("설 근접도", "설 2주 이내(명절 수요)", "설 비시즌"),
    "is_school_demand":   ("학교 급식 수요기", "개학 수요(3·9월 급식 증가)", "급식 비수기"),
    "is_summer_break":    ("여름방학 급식 중단", "여름방학으로 급식 수요 감소", "급식 정상 운영"),
}

ITEM_NAMES = {
    "cabbage": "배추", "radish": "무", "onion": "양파",
    "green_onion": "대파", "garlic": "마늘",
    "potato": "감자", "sweet_potato": "고구마",
    "pepper": "고추", "fresh_pepper": "풋고추",
    "tomato": "토마토", "cucumber": "오이",
    "zucchini": "애호박", "carrot": "당근",
    "spinach": "시금치", "lettuce": "상추",
    "perilla": "깻잎", "watermelon": "수박",
    "chamoe": "참외", "sesame": "참깨",
    "apple": "사과", "pear": "배",
    "grape": "포도", "strawberry": "딸기",
}


def _josa(name: str, josa_pair: tuple[str, str]) -> str:
    """받침 여부에 따라 조사 선택. josa_pair = (받침있을때, 받침없을때)"""
    last = name[-1] if name else ""
    code = ord(last) - 0xAC00
    if 0 <= code < 11172:
        return josa_pair[0] if (code % 28) != 0 else josa_pair[1]
    return josa_pair[1]


def factor_to_korean(factor: dict) -> str:
    """단일 top_factor → 한국어 설명 문자열"""
    fname = factor.get("factor", "")
    direction = factor.get("direction", "up")  # "up" or "down"
    importance = factor.get("importance", 0.0)

    entry = FEATURE_LABELS.get(fname)
    if not entry:
        return fname

    label, up_msg, down_msg = entry
    msg = up_msg if direction == "up" else down_msg
    return msg


def build_summary_text(
    item_code: str,
    direction_14d: str,
    up_probability: float,
    top_factors: list,
    confidence: str = "medium",
) -> str:
    """예측 결과 + top_factors → 한국어 자연어 요약 1~3문장"""
    item_name = ITEM_NAMES.get(item_code, item_code)
    up_probability = up_probability or 0.5
    prob_pct = round(up_probability * 100)

    # 방향 문장
    eun_neun = _josa(item_name, ("은", "는"))
    dir_map = {
        "up":      f"{item_name}{eun_neun} 향후 14일 내 상승 가능성이 {prob_pct}%입니다.",
        "down":    f"{item_name}{eun_neun} 향후 14일 내 하락 가능성이 {100-prob_pct}%입니다.",
        "neutral": f"{item_name}{eun_neun} 향후 14일 내 보합 흐름이 예상됩니다.",
    }
    first = dir_map.get(direction_14d, dir_map["neutral"])

    # 신뢰도
    conf_map = {"high": "신뢰도 높음", "medium": "신뢰도 보통", "low": "신뢰도 낮음"}
    conf_str = conf_map.get(confidence, "신뢰도 보통")

    # 주요 요인 Top2 문장
    factor_msgs = []
    for f in (top_factors or [])[:2]:
        msg = factor_to_korean(f)
        if msg:
            factor_msgs.append(msg)

    second = ""
    if factor_msgs:
        second = "주요 요인: " + ", ".join(factor_msgs) + "."

    return " ".join(filter(None, [first, second, f"({conf_str})"]))


def factors_to_display(top_factors: list) -> list[dict]:
    """top_factors → UI 표시용 딕셔너리 리스트"""
    result = []
    for f in (top_factors or [])[:5]:
        fname = f.get("factor", "")
        entry = FEATURE_LABELS.get(fname)
        if not entry:
            continue
        label, up_msg, down_msg = entry
        direction = f.get("direction", "up")
        result.append({
            "label": label,
            "message": up_msg if direction == "up" else down_msg,
            "direction": direction,
            "importance": round(f.get("importance", 0), 3),
        })
    return result


PUBLIC_ITEM_NAMES = {
    "cabbage": "배추",
    "radish": "무",
    "onion": "양파",
    "green_onion": "대파",
    "garlic": "마늘",
    "potato": "감자",
    "sweet_potato": "고구마",
    "pepper": "고추",
    "fresh_pepper": "풋고추",
    "tomato": "토마토",
    "cucumber": "오이",
    "zucchini": "애호박",
    "carrot": "당근",
    "spinach": "시금치",
    "lettuce": "상추",
    "perilla": "깻잎",
    "watermelon": "수박",
    "chamoe": "참외",
    "sesame": "참깨",
    "apple": "사과",
    "pear": "배",
    "grape": "포도",
    "strawberry": "딸기",
}

PUBLIC_FEATURE_LABELS = {
    "price_lag_model": ("최근 가격 흐름", "최근 거래가가 올라 예측값을 위로 밀고 있습니다.", "최근 거래가가 내려 예측값을 아래로 당기고 있습니다."),
    "risk_overlay": ("지역 위험 신호", "주산지 위험 신호가 가격 상승 압력으로 반영됐습니다.", "주산지 위험 신호가 약해져 하락 또는 안정 쪽으로 반영됐습니다."),
    "price_ma7": ("단기 가격 추세", "최근 1주 가격이 상승 쪽으로 움직입니다.", "최근 1주 가격이 하락 쪽으로 움직입니다."),
    "price_ma14": ("중기 가격 추세", "최근 2주 가격 흐름이 상승 쪽입니다.", "최근 2주 가격 흐름이 하락 쪽입니다."),
    "price_ma28": ("월간 가격 추세", "최근 한 달 가격 기준선이 높아지고 있습니다.", "최근 한 달 가격 기준선이 낮아지고 있습니다."),
    "ret_1d": ("하루 가격 변화", "직전 거래일 가격 반응이 강합니다.", "직전 거래일 가격 반응이 약합니다."),
    "ret_7d": ("주간 가격 변화", "주간 변동률이 상승 압력으로 잡혔습니다.", "주간 변동률이 하락 압력으로 잡혔습니다."),
    "ret_14d": ("2주 가격 변화", "2주 변동률이 상승 판단에 영향을 줬습니다.", "2주 변동률이 하락 판단에 영향을 줬습니다."),
    "volatility_7d": ("단기 변동성", "최근 가격 흔들림이 커져 상승 리스크가 있습니다.", "최근 가격 흔들림이 줄어 안정 쪽으로 봅니다."),
    "volatility_14d": ("중기 변동성", "2주 변동성이 커져 가격이 튈 가능성이 있습니다.", "2주 변동성이 낮아져 안정 쪽으로 봅니다."),
    "price_vs_avg_year": ("평년 대비 가격", "평년보다 높은 가격대가 유지되고 있습니다.", "평년보다 낮은 가격대가 이어지고 있습니다."),
    "price_vs_prev_year": ("전년 대비 가격", "전년보다 비싼 구간이라 상승 압력이 남아 있습니다.", "전년보다 낮은 구간이라 상승 압력이 약합니다."),
    "ma7_vs_ma28": ("단기-월간 가격 차이", "단기 가격이 월간 기준보다 강합니다.", "단기 가격이 월간 기준보다 약합니다."),
    "sin_month": ("계절 구간", "현재 계절 구간이 가격 상승 쪽으로 작용합니다.", "현재 계절 구간이 가격 하락 쪽으로 작용합니다."),
    "cos_month": ("계절 수요", "계절 수요가 가격을 받쳐주는 구간입니다.", "계절 수요가 약한 구간입니다."),
    "w_avg_temp": ("기온 영향", "기온 조건이 생육과 출하에 부담을 줍니다.", "기온 조건 부담이 크지 않습니다."),
    "w_precipitation": ("강수 영향", "비와 수분 조건이 출하 부담으로 잡혔습니다.", "비와 수분 조건 부담이 낮습니다."),
    "w_temp_dev": ("평년 대비 기온", "평년과 다른 기온이 가격 변동 요인입니다.", "평년 대비 기온 부담이 약합니다."),
    "w_temp_ma7": ("7일 기온 흐름", "최근 기온 흐름이 생육 부담을 키웁니다.", "최근 기온 흐름이 안정 쪽입니다."),
    "w_precip_ma7": ("7일 강수 흐름", "최근 강수 흐름이 작업과 출하에 부담입니다.", "최근 강수 흐름 부담이 낮습니다."),
    "w_heat_alert_7d": ("폭염 신호", "폭염 신호가 품질과 출하 리스크를 키웁니다.", "폭염 신호가 약합니다."),
    "w_cold_alert_7d": ("한파 신호", "한파 신호가 생육 리스크로 잡혔습니다.", "한파 신호가 약합니다."),
    "w_heavy_rain_7d": ("호우 신호", "호우 신호가 수확과 물류 부담을 키웁니다.", "호우 신호가 약합니다."),
    "kosis_area_dev": ("재배면적 변화", "재배면적 변화가 공급 부담으로 반영됐습니다.", "재배면적 변화가 공급 여유로 반영됐습니다."),
    "kosis_prod_dev": ("생산량 변화", "생산량 변화가 공급 부족 쪽으로 잡혔습니다.", "생산량 변화가 공급 여유 쪽으로 잡혔습니다."),
    "kosis_supply_risk": ("공급 위험", "공급 위험이 가격 상승 압력입니다.", "공급 위험이 낮아 안정 쪽입니다."),
    "mkt_volume_kg": ("도매시장 거래량", "거래량 변화가 수급 긴장으로 잡혔습니다.", "거래량 변화가 수급 완화로 잡혔습니다."),
    "mkt_volume_ma7": ("주간 거래량", "최근 거래량 흐름이 가격을 밀어 올립니다.", "최근 거래량 흐름이 가격을 눌러줍니다."),
    "mkt_volume_ma28": ("월간 거래량", "월간 거래량 흐름이 수급 부담입니다.", "월간 거래량 흐름이 수급 안정 쪽입니다."),
    "mkt_volume_vs_avg": ("평균 대비 거래량", "평균 대비 거래량이 수급 긴장으로 해석됩니다.", "평균 대비 거래량이 수급 완화로 해석됩니다."),
    "mkt_volume_trend": ("거래량 추세", "거래량 추세가 가격 상승 쪽입니다.", "거래량 추세가 가격 하락 쪽입니다."),
    "days_to_kimjang": ("김장 수요", "김장 수요가 가까워 가격 상승 요인입니다.", "김장 수요 영향이 약합니다."),
    "is_kimjang_season": ("김장철", "김장철 수요가 가격을 받쳐줍니다.", "김장철 영향이 약합니다."),
    "kimjang_proximity": ("김장 근접도", "김장 시점이 가까워 수요 압력이 있습니다.", "김장 시점 영향이 낮습니다."),
    "days_to_chuseok": ("추석 수요", "명절 수요가 가격을 받쳐줍니다.", "명절 수요 영향이 약합니다."),
    "chuseok_proximity": ("추석 근접도", "추석 근접 수요가 반영됐습니다.", "추석 근접 수요가 약합니다."),
    "days_to_seol": ("설 수요", "설 명절 수요가 가격을 받쳐줍니다.", "설 명절 수요 영향이 약합니다."),
    "seol_proximity": ("설 근접도", "설 근접 수요가 반영됐습니다.", "설 근접 수요가 약합니다."),
    "is_school_demand": ("급식 수요", "급식 수요가 가격을 받쳐주는 구간입니다.", "급식 수요 영향이 약합니다."),
    "is_summer_break": ("방학 수요", "방학으로 급식 수요가 줄어드는 구간입니다.", "방학 영향이 낮습니다."),
}

PUBLIC_COLUMN_FACTOR_LABELS = {
    0: "기준 가격 흐름",
    1: "최근 가격 반응",
    2: "단기 가격 모멘텀",
    3: "중기 가격 모멘텀",
    4: "가격 변동 속도",
    5: "가격 변동성",
    6: "평균가 대비 괴리",
    7: "전년 대비 가격 차이",
    8: "중기 가격 차이",
    9: "가격 추세 전환",
    10: "계절 수요 구간",
    11: "계절성 보조 신호",
    12: "수요 이벤트",
    13: "명절·급식 수요",
    14: "공급 여건",
    15: "생산량 압력",
    16: "산지·재배 여건",
    17: "공급·출하 압력",
    18: "도매시장 거래량",
    19: "거래량 추세",
    20: "기상 스트레스",
    21: "강수·작업 여건",
    22: "기상·재해 변수",
}


def _public_josa(name: str) -> str:
    code = ord(name[-1]) - 0xAC00 if name else -1
    return "은" if 0 <= code < 11172 and code % 28 else "는"


def _column_factor_index(name: str) -> int | None:
    if not name.startswith("Column_"):
        return None
    try:
        return int(name.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def public_factor_label(name: str) -> str:
    entry = PUBLIC_FEATURE_LABELS.get(name)
    if entry:
        return entry[0]
    column_index = _column_factor_index(name)
    if column_index is not None:
        return PUBLIC_COLUMN_FACTOR_LABELS.get(column_index, "AI 종합 판단")
    return "AI 종합 판단" if name else "기타 요인"


def public_factor_message(name: str, direction: str = "up") -> str:
    entry = PUBLIC_FEATURE_LABELS.get(name)
    if entry:
        return entry[1] if direction == "up" else entry[2]
    column_index = _column_factor_index(name)
    label = public_factor_label(name)
    if column_index is not None:
        if direction == "down":
            return f"{label}이 현재 예측에서는 가격을 낮추거나 안정시키는 쪽으로 작용했습니다."
        return f"{label}이 현재 예측에서는 가격을 올리거나 흔드는 쪽으로 작용했습니다."
    if direction == "down":
        return "AI가 여러 입력값을 종합했을 때 하락 또는 안정 쪽 신호가 더 강했습니다."
    return "AI가 여러 입력값을 종합했을 때 상승 또는 변동 쪽 신호가 더 강했습니다."


def public_factor_payload(factor: dict) -> dict:
    name = str(factor.get("factor") or "")
    direction = str(factor.get("direction") or "up")
    importance = factor.get("importance", factor.get("contribution", 0))
    try:
        importance_value = round(float(importance or 0), 3)
    except (TypeError, ValueError):
        importance_value = 0
    return {
        "label": public_factor_label(name),
        "message": public_factor_message(name, direction),
        "direction": direction,
        "importance": importance_value,
        "raw_factor": name,
    }


def factor_to_korean(factor: dict) -> str:
    return public_factor_message(str(factor.get("factor") or ""), str(factor.get("direction") or "up"))


def build_summary_text(
    item_code: str,
    direction_14d: str,
    up_probability: float,
    top_factors: list,
    confidence: str = "medium",
) -> str:
    item_name = PUBLIC_ITEM_NAMES.get(item_code, item_code)
    up_probability = up_probability or 0.5
    if direction_14d == "down":
        first = f"{item_name}{_public_josa(item_name)} 앞으로 14일 기준 하락 가능성이 {round((1 - up_probability) * 100)}%로 계산됐습니다."
    elif direction_14d == "up":
        first = f"{item_name}{_public_josa(item_name)} 앞으로 14일 기준 상승 가능성이 {round(up_probability * 100)}%로 계산됐습니다."
    else:
        first = f"{item_name}{_public_josa(item_name)} 앞으로 14일 기준 뚜렷한 방향보다 보합 가능성이 큽니다."

    factors = [
        public_factor_message(str(f.get("factor") or ""), str(f.get("direction") or "up"))
        for f in (top_factors or [])[:2]
        if isinstance(f, dict)
    ]
    confidence_label = {"high": "신뢰도 높음", "medium": "신뢰도 보통", "low": "신뢰도 낮음"}.get(confidence, "신뢰도 보통")
    second = " ".join(factors)
    return " ".join(part for part in [first, second, f"({confidence_label})"] if part)


def factors_to_display(top_factors: list) -> list[dict]:
    return [
        public_factor_payload(f)
        for f in (top_factors or [])[:5]
        if isinstance(f, dict)
    ]
