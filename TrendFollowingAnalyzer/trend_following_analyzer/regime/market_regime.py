from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from ..indicators import add_moving_average_indicators

BULL = "BULL"
NEUTRAL = "NEUTRAL"
BEAR = "BEAR"
INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class MarketRegimeSnapshot:
    market: str
    regime: str
    market_eligible: bool
    index_close: float | None
    index_ma50: float | None
    index_ma150: float | None
    index_ma150_slope_pct: float | None
    index_close_vs_ma150_pct: float | None
    index_ma50_vs_ma150_pct: float | None
    lecture_ma150_position_pass: bool
    lecture_ma150_slope_pass: bool
    experimental_slope_threshold_pass: bool
    experimental_ma50_alignment_pass: bool
    regime_reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _num(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def classify_market_regime(
    df: pd.DataFrame,
    *,
    market: str,
    ma_short: int = 50,
    ma_long: int = 150,
    slope_lookback: int = 20,
    experimental_slope_threshold_pct: float = 0.30,
) -> MarketRegimeSnapshot:
    """Classify BULL/NEUTRAL/BEAR from the lecture's index/30-week-MA rule.

    Active lecture-core gate:
      BULL: index close > MA150 AND MA150 slope > 0
      BEAR: index close < MA150 AND MA150 slope < 0
      NEUTRAL: mixed/flat cases

    Experimental features are recorded but do not change `regime`.
    """
    if experimental_slope_threshold_pct < 0:
        raise ValueError("experimental_slope_threshold_pct must be non-negative")

    enriched = add_moving_average_indicators(
        df,
        ma_short=ma_short,
        ma_long=ma_long,
        slope_lookback=slope_lookback,
    )
    if enriched.empty:
        return MarketRegimeSnapshot(
            market=market,
            regime=INSUFFICIENT,
            market_eligible=False,
            index_close=None,
            index_ma50=None,
            index_ma150=None,
            index_ma150_slope_pct=None,
            index_close_vs_ma150_pct=None,
            index_ma50_vs_ma150_pct=None,
            lecture_ma150_position_pass=False,
            lecture_ma150_slope_pass=False,
            experimental_slope_threshold_pass=False,
            experimental_ma50_alignment_pass=False,
            regime_reason="지수 데이터 없음",
        )

    last = enriched.iloc[-1]
    close = _num(last.get("close"))
    ma50 = _num(last.get("ma50"))
    ma150 = _num(last.get("ma150"))
    slope = _num(last.get("ma150_slope_pct"))
    distance = _num(last.get("close_vs_ma150_pct"))
    ma50_distance = _num(last.get("ma50_vs_ma150_pct"))

    if close is None or ma150 is None or slope is None:
        regime = INSUFFICIENT
        reason = "MA150 또는 MA150 기울기 계산 데이터 부족"
        position_pass = False
        slope_pass = False
    else:
        position_pass = close > ma150
        slope_pass = slope > 0
        if close > ma150 and slope > 0:
            regime = BULL
            reason = "LECTURE_CORE: 지수가 MA150 위이고 MA150 기울기가 상승"
        elif close < ma150 and slope < 0:
            regime = BEAR
            reason = "LECTURE_CORE: 지수가 MA150 아래이고 MA150 기울기가 하락"
        else:
            regime = NEUTRAL
            reason = "LECTURE_CORE 혼합: 지수 위치와 MA150 기울기가 같은 방향이 아님"

    strict_pass = bool(
        close is not None
        and ma150 is not None
        and slope is not None
        and (
            (close > ma150 and slope >= experimental_slope_threshold_pct)
            or (close < ma150 and slope <= -experimental_slope_threshold_pct)
        )
    )
    ma50_alignment = bool(ma50 is not None and ma150 is not None and ma50 > ma150)

    return MarketRegimeSnapshot(
        market=str(market).upper(),
        regime=regime,
        market_eligible=regime == BULL,
        index_close=close,
        index_ma50=ma50,
        index_ma150=ma150,
        index_ma150_slope_pct=slope,
        index_close_vs_ma150_pct=distance,
        index_ma50_vs_ma150_pct=ma50_distance,
        lecture_ma150_position_pass=position_pass,
        lecture_ma150_slope_pass=slope_pass,
        experimental_slope_threshold_pass=strict_pass,
        experimental_ma50_alignment_pass=ma50_alignment,
        regime_reason=reason,
    )
