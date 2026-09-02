from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from chartsel.analysis.market_regime import classify_market_regime
from chartsel.analysis.relative_strength import relative_strength_context
from chartsel.indicators.candlestick import candle_features
from chartsel.indicators.moving_average import add_moving_averages
from chartsel.indicators.volume import add_volume_features, volume_context
from chartsel.structure.pivots import find_pivots
from chartsel.structure.support_resistance import breakout_retest_state, support_resistance
from chartsel.structure.trend import trend_context

from .buy_day_guide import build_buy_day_guide
from .config import CloseBetConfig, DEFAULT_CONFIG
from .models import CloseBetResult


MA_CFG = {
    "short": 5,
    "life": 20,
    "mid": 60,
    "long": 120,
    "slope_lookback": 5,
    "distance_warn_life_pct": 0.12,
    "distance_warn_long_pct": 0.25,
}
VOL_CFG = {"avg_window": 20, "confirm_ratio": 1.5, "strong_ratio": 2.0, "dry_ratio": 0.7}
SR_CFG = {
    "pattern_lookback": 180,
    "level_tolerance_pct": 0.02,
    "min_level_touches": 2,
    "breakout_buffer_pct": 0.005,
}
UNKNOWN_SECTORS = {"", "기타/미분류", "UNKNOWN", "NAN", "NONE"}


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x = add_moving_averages(x, MA_CFG)
    x = add_volume_features(x, VOL_CFG)
    x = find_pivots(x, left=3, right=3)
    return x


def _num(value: Any, default: float = np.nan) -> float:
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _market_score(regime: str) -> float:
    return {
        "uptrend": 85.0,
        "range": 58.0,
        "volatile": 48.0,
        "downtrend": 30.0,
    }.get(str(regime), 50.0)


def _liquidity_score(source_rank: int | None, universe_size: int) -> float:
    if source_rank is None or universe_size <= 1:
        return 50.0
    rank = max(1, min(int(source_rank), int(universe_size)))
    return round(100.0 - (rank - 1) / max(1, universe_size - 1) * 50.0, 2)


def _sector_available(name: str, raw_score: float) -> bool:
    normalized = str(name or "").strip()
    if normalized.upper() in UNKNOWN_SECTORS or normalized in UNKNOWN_SECTORS:
        return False
    if normalized == "ETF/ETN":
        return False
    return np.isfinite(raw_score)


def _weighted_score(components: list[tuple[float, float, bool]]) -> float:
    """Normalize only over available evidence; missing sector never contributes fake 50."""
    weighted = 0.0
    weight_sum = 0.0
    for value, weight, available in components:
        if not available or not np.isfinite(value) or weight <= 0:
            continue
        weighted += float(value) * float(weight)
        weight_sum += float(weight)
    if weight_sum <= 0:
        return 0.0
    return round(max(0.0, min(100.0, weighted / weight_sum)), 2)


def _structure_score(x: pd.DataFrame, cfg: CloseBetConfig) -> tuple[float, dict[str, Any], list[str], list[str]]:
    t = trend_context(x, MA_CFG)
    sr = support_resistance(x, SR_CFG)
    br = breakout_retest_state(x, sr, SR_CFG)
    row = x.iloc[-1]
    close = float(row["Close"])
    ma5 = _num(row.get("MA5"))
    ma20 = _num(row.get("MA20"))

    high60 = _num(pd.to_numeric(x["High"], errors="coerce").tail(60).max())
    distance_high = close / high60 - 1.0 if np.isfinite(high60) and high60 > 0 else np.nan

    score = 50.0
    reasons: list[str] = []
    risks: list[str] = []

    if t.get("above_life_ma"):
        score += 10
        reasons.append("20일선 위")
    else:
        score -= 10
        risks.append("20일선 아래")

    if t.get("higher_lows"):
        score += 10
        reasons.append("저점 상승")
    if t.get("higher_highs"):
        score += 5
        reasons.append("고점 상승")
    if t.get("down_structure"):
        score -= 18
        risks.append("고점·저점 동반 하락")

    if np.isfinite(distance_high):
        if distance_high >= -cfg.near_high_pct:
            score += 15
            reasons.append("60일 고점 근처")
        elif distance_high < -cfg.max_confirmed_distance_60d_high_pct:
            score -= 20
            risks.append("고점과 거리 큼")

    if br.get("breakout_level"):
        score += 8
        reasons.append("저항 돌파")
    if br.get("retest_support_level"):
        score += 8
        reasons.append("돌파 후 지지 전환")
    if br.get("breakdown_level"):
        score -= 18
        risks.append("지지 이탈")

    life_gap = _num(t.get("life_gap_pct"))
    if np.isfinite(life_gap) and life_gap >= cfg.overextended_ma20_pct:
        score -= 3
        risks.append("20일선 과도 이격")

    candle = candle_features(row)
    if candle["bullish"] and candle["close_location"] >= 0.75:
        score += 5
        reasons.append("종가가 당일 고가권")
    if candle["upper_wick_ratio"] >= 0.45:
        score -= 7
        risks.append("긴 윗꼬리")

    details = {
        "trend": t,
        "sr": sr,
        "breakout": br,
        "distance_60d_high_pct": distance_high,
        "ma5": ma5 if np.isfinite(ma5) else None,
        "ma20": ma20 if np.isfinite(ma20) else None,
    }
    return round(max(0.0, min(100.0, score)), 2), details, reasons, risks


def _classify_status(
    *,
    score: float,
    regime: str,
    stock_rs_score: float,
    structure_score: float,
    sector_available: bool,
    sector_score: float,
    distance_60d_high_pct: float,
    near_high_or_breakout: bool,
    cfg: CloseBetConfig,
) -> str:
    far_from_high = (
        np.isfinite(distance_60d_high_pct)
        and distance_60d_high_pct < -cfg.max_confirmed_distance_60d_high_pct
    )
    sector_ok = (not sector_available) or sector_score >= cfg.min_sector_score
    strong_sector_ok = (not sector_available) or sector_score >= cfg.strong_sector_score

    confirmed_score_needed = cfg.confirmed_score
    rs_needed = cfg.min_stock_rs
    if regime == "range":
        confirmed_score_needed = max(confirmed_score_needed, cfg.range_confirmed_score)
        rs_needed = max(rs_needed, cfg.range_min_stock_rs)
    elif regime == "downtrend":
        confirmed_score_needed = max(confirmed_score_needed, cfg.downtrend_confirmed_score)
        rs_needed = max(rs_needed, cfg.downtrend_min_stock_rs)

    confirmed_gate = (
        score >= confirmed_score_needed
        and stock_rs_score >= rs_needed
        and structure_score >= cfg.min_structure_score
        and sector_ok
        and not far_from_high
    )
    strong_gate = (
        confirmed_gate
        and score >= cfg.strong_confirmed_score
        and stock_rs_score >= cfg.strong_stock_rs
        and structure_score >= cfg.strong_structure_score
        and strong_sector_ok
        and near_high_or_breakout
        and regime != "downtrend"
    )

    if strong_gate:
        return "STRONG_CONFIRMED"
    if confirmed_gate:
        return "CONFIRMED"
    if score >= cfg.watch_score:
        return "WATCH"
    return "REJECTED"


class CloseBetAnalyzer:
    """Completed-daily-data selector + manual buy-day price guide.

    The same analyzer/gates are used by both screen and range runs.
    V2 intentionally does not auto-score the intended buy day's intraday chart.
    """

    def __init__(self, cfg: CloseBetConfig = DEFAULT_CONFIG):
        cfg.validate()
        self.cfg = cfg

    def analyze(
        self,
        *,
        ticker: str,
        name: str,
        market: str,
        stock_df: pd.DataFrame,
        market_df: pd.DataFrame,
        sector_context: dict[str, Any] | None,
        source_rank: int | None,
        universe_size: int,
    ) -> CloseBetResult:
        if stock_df is None or stock_df.empty or len(stock_df) < 130:
            raise ValueError("CloseBetAnalyzer requires at least 130 daily bars")

        x = prepare_features(stock_df)
        m = prepare_features(market_df)
        date = pd.Timestamp(x.index[-1]).strftime("%Y-%m-%d")

        regime = classify_market_regime(m, MA_CFG)
        market_score = _market_score(regime)
        rs = relative_strength_context(x, m)
        stock_rs_score = _num(rs.get("score"), 50.0)

        sector_context = sector_context or {}
        sector_name = str(sector_context.get("sector_name", "기타/미분류"))
        sector_score_raw = _num(sector_context.get("sector_composite_score"))
        sector_available = _sector_available(sector_name, sector_score_raw)
        sector_score = sector_score_raw if sector_available else np.nan
        sector_rank_raw = _num(sector_context.get("sector_composite_rank"))
        sector_rank = None if (not sector_available or not np.isfinite(sector_rank_raw)) else sector_rank_raw

        liquidity_score = _liquidity_score(source_rank, universe_size)
        structure_score, structure, reasons, risks = _structure_score(x, self.cfg)

        v = volume_context(x, VOL_CFG)
        rel_vol = _num(v.get("relative_volume"))
        volume_score = 50.0
        if v.get("bullish_confirm"):
            volume_score += 5.0
            reasons.append("상승 거래량 확인")
        if v.get("dry_volume"):
            volume_score -= 3.0
        if v.get("distribution_hint"):
            volume_score -= 25.0
            risks.append("고거래량 윗꼬리 분배 위험")
        if v.get("high_volume_stall"):
            volume_score -= 12.0
            risks.append("고거래량 가격 정체")
        volume_score = round(max(0.0, min(100.0, volume_score)), 2)

        score = _weighted_score(
            [
                (market_score, self.cfg.market_weight, True),
                (sector_score, self.cfg.sector_weight, sector_available),
                (stock_rs_score, self.cfg.stock_rs_weight, True),
                (liquidity_score, self.cfg.liquidity_weight, True),
                (structure_score, self.cfg.structure_weight, True),
                (volume_score, self.cfg.volume_weight, True),
            ]
        )

        distance_high = _num(structure.get("distance_60d_high_pct"))
        breakout = structure.get("breakout", {})
        near_high_or_breakout = (
            (np.isfinite(distance_high) and distance_high >= -self.cfg.near_high_pct)
            or bool(breakout.get("breakout_level"))
            or bool(breakout.get("retest_support_level"))
        )
        status = _classify_status(
            score=score,
            regime=regime,
            stock_rs_score=stock_rs_score,
            structure_score=structure_score,
            sector_available=sector_available,
            sector_score=sector_score if np.isfinite(sector_score) else 0.0,
            distance_60d_high_pct=distance_high,
            near_high_or_breakout=near_high_or_breakout,
            cfg=self.cfg,
        )

        if regime == "uptrend":
            reasons.append("시장 상승추세")
        elif regime == "range":
            risks.append("횡보장: CONFIRMED 강화 기준 적용")
        elif regime == "downtrend":
            risks.append("시장 하락추세: CONFIRMED 강화 기준 적용")

        if sector_available:
            if sector_score >= self.cfg.strong_sector_score:
                reasons.append("강한 섹터")
        else:
            risks.append("섹터 정보 없음: 섹터 점수 제외")
        if stock_rs_score >= self.cfg.strong_stock_rs:
            reasons.append("시장 대비 강한 종목")

        close = float(x["Close"].iloc[-1])
        nearest_support = structure["sr"].get("nearest_support")
        nearest_resistance = structure["sr"].get("nearest_resistance")
        guide = build_buy_day_guide(
            reference_close=close,
            ma5=structure.get("ma5"),
            nearest_support=nearest_support,
            cfg=self.cfg,
        )

        return CloseBetResult(
            actual_date=date,
            ticker=str(ticker).zfill(6),
            name=name,
            market=market,
            status=status,
            score=score,
            market_regime=regime,
            market_score=market_score,
            sector_name=sector_name,
            sector_available=sector_available,
            sector_score=None if not sector_available else round(float(sector_score), 2),
            sector_rank=sector_rank,
            stock_rs_score=round(stock_rs_score, 2),
            liquidity_score=liquidity_score,
            source_rank=source_rank,
            structure_score=structure_score,
            volume_score=volume_score,
            close=round(close, 2),
            ma5=structure.get("ma5"),
            ma20=structure.get("ma20"),
            distance_60d_high_pct=(
                None if not np.isfinite(distance_high) else round(float(distance_high) * 100.0, 3)
            ),
            nearest_support=None if nearest_support is None else round(float(nearest_support), 2),
            nearest_resistance=None if nearest_resistance is None else round(float(nearest_resistance), 2),
            relative_volume=None if not np.isfinite(rel_vol) else round(rel_vol, 3),
            reasons=reasons,
            risks=risks,
            guide=guide,
        )
