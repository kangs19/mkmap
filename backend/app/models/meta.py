"""
품목별 메타데이터 — KAMIS/KOSIS/KMA API 실데이터 기반 피처 집계 테이블
매일 파이프라인에서 갱신. 예측 모델 피처 & API 응답으로 직접 서빙.
"""
from sqlalchemy import String, Float, Integer, DateTime, JSON, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from typing import Optional
from app.database import Base


class ItemMeta(Base):
    __tablename__ = "item_meta"

    item_code: Mapped[str] = mapped_column(String(50), primary_key=True)

    # ── 기본 정보 ─────────────────────────────────────────────────────────
    item_name:     Mapped[str]   = mapped_column(String(100))
    kamis_productno: Mapped[str] = mapped_column(String(20))   # KAMIS 도매 productno
    unit:          Mapped[str]   = mapped_column(String(20))   # 거래 단위 (10kg 등)
    category_name: Mapped[str]   = mapped_column(String(50))   # 채소류 등
    main_region:   Mapped[str]   = mapped_column(String(50), default="")  # 주산지

    # ── KAMIS 가격 피처 ───────────────────────────────────────────────────
    price_today:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 당일 도매가 (원)
    price_avg_7d:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 7일 이동평균
    price_avg_30d:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 30일 이동평균
    price_avg_90d:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 90일 이동평균
    price_std_30d:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 30일 표준편차
    price_cv_30d:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 변동계수 (std/mean)
    price_min_52w:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 52주 최저
    price_max_52w:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 52주 최고
    price_pct_of_52w_range: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 현재가 52주 범위 내 위치 (0~1)
    price_prev_year:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 전년 동기 가격
    yoy_change_pct:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 전년 대비 변화율 (%)
    mom_7d:            Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 7일 모멘텀 (현재/7일전)
    mom_30d:           Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 30일 모멘텀
    price_vs_ma30_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 현재가 vs MA30 (%)
    trend_slope_30d:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 30일 회귀 기울기 (원/일)
    seasonal_index:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # 계절성 지수 (동월평균/연평균)
    data_days_count:   Mapped[Optional[int]]   = mapped_column(Integer, nullable=True) # 보유 가격 데이터 일수

    # ── KOSIS 생산 피처 ───────────────────────────────────────────────────
    area_ha_y1:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 전년 재배면적 (ha)
    area_ha_y2:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 2년전
    area_ha_y3:          Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 3년전
    production_ton_y1:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 전년 생산량 (톤)
    production_ton_y2:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    production_ton_y3:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    yield_per_ha_y1:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 단위면적 생산량 (kg/10a)
    area_yoy_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 재배면적 전년비 (%)
    prod_yoy_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 생산량 전년비 (%)

    # ── KMA 기상 피처 (주산지 대표) ───────────────────────────────────────
    weather_temp_avg_7d:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 7일 평균기온
    weather_precip_7d:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 7일 강수량합 (mm)
    weather_temp_anomaly_7d: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # 평년 대비 기온 이상 (℃)
    weather_stress_score:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 기상 스트레스 (0~1)
    weather_alert_count_7d: Mapped[Optional[int]]   = mapped_column(Integer, nullable=True) # 7일 기상 특보 횟수

    # ── 종합 위험도 피처 ──────────────────────────────────────────────────
    supply_risk_score:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 공급 위험도 (0~1)
    price_risk_score:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 가격 이상 위험도 (0~1)
    overall_risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 종합 위험도 (0~1)
    risk_level:         Mapped[str]              = mapped_column(String(20), default="unknown")  # low/medium/high/critical
    risk_factors:       Mapped[Optional[dict]]   = mapped_column(JSON, nullable=True)  # 위험요인 상세

    # ── 메타 정보 ─────────────────────────────────────────────────────────
    price_data_from:  Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 가격 데이터 시작일
    price_data_to:    Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 가격 데이터 종료일
    kosis_latest_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # KOSIS 최근 확정연도
    confidence:       Mapped[str]            = mapped_column(String(20), default="draft")  # draft/partial/full
    updated_at:       Mapped[datetime]       = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
