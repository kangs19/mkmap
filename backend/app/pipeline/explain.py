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
}


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
    prob_pct = round(up_probability * 100)

    # 방향 문장
    dir_map = {
        "up":      f"{item_name} 가격은 향후 14일 내 **상승**할 가능성이 {prob_pct}%입니다.",
        "down":    f"{item_name} 가격은 향후 14일 내 **하락**할 가능성이 {100-prob_pct}%입니다.",
        "neutral": f"{item_name} 가격은 향후 14일 내 **보합** 흐름이 예상됩니다.",
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
