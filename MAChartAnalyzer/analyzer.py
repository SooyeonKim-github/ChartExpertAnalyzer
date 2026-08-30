from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from config import MAConfig


@dataclass
class MAAnalysisResult:
    ticker: str
    name: str
    market: str
    requested_date: str
    actual_date: str
    status: str
    score: int
    timing_score: int
    primary_signal: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = {
            "Ticker": self.ticker,
            "Name": self.name,
            "Market": self.market,
            "Requested_Date": self.requested_date,
            "Actual_Date": self.actual_date,
            "Status": self.status,
            "Score": self.score,
            "Timing_Score": self.timing_score,
            "Primary_Signal": self.primary_signal,
            "Reasons": " | ".join(self.reasons),
            "Warnings": " | ".join(self.warnings),
        }
        row.update(self.metrics)
        return row


def _pct_change(now: float, before: float) -> float:
    if not math.isfinite(now) or not math.isfinite(before) or before == 0:
        return float("nan")
    return (now / before - 1.0) * 100.0


def _cross_count(a: pd.Series, b: pd.Series, lookback: int) -> int:
    diff = (a - b).dropna().tail(lookback)
    if len(diff) < 2:
        return 0
    signs = np.sign(diff.to_numpy(dtype=float))
    for i in range(1, len(signs)):
        if signs[i] == 0:
            signs[i] = signs[i - 1]
    changes = 0
    for i in range(1, len(signs)):
        if signs[i - 1] == 0 or signs[i] == 0:
            continue
        if signs[i - 1] != signs[i]:
            changes += 1
    return changes


class MAChartSignalAnalyzer:
    """Lecture-derived moving-average BUY analyzer, V2.

    V2 lessons from the first range backtest:
    - BOX_BREAKOUT stays the main confirmed trigger.
    - ordinary PULLBACK_RECLAIM and SQUEEZE_BREAKOUT are setups (WATCH), not
      enough by themselves for a confirmed buy.
    - a pullback becomes confirmable only with strong candle separation.
    - box retest must happen *after* a prior breakout, never on the same candle.
    - box/prior-high/retest points are not double-counted.
    """

    def __init__(self, cfg: MAConfig) -> None:
        self.cfg = cfg

    def analyze(
        self,
        ticker: str,
        name: str,
        market: str,
        requested_date: str,
        df: pd.DataFrame,
    ) -> MAAnalysisResult:
        cfg = self.cfg
        actual_date = df.index[-1].strftime("%Y-%m-%d") if len(df) else ""
        if len(df) < cfg.min_history_bars:
            return MAAnalysisResult(
                ticker, name, market, requested_date, actual_date,
                "REJECTED", 0, 0, "INSUFFICIENT_HISTORY",
                warnings=[f"히스토리 부족: {len(df)}봉 < {cfg.min_history_bars}봉"],
            )

        d = df.copy()
        short_col = f"MA{cfg.short_ma_period}"
        long_col = f"MA{cfg.long_ma_period}"
        d[short_col] = d["Close"].rolling(cfg.short_ma_period).mean()
        d[long_col] = d["Close"].rolling(cfg.long_ma_period).mean()
        d["_body"] = (d["Close"] - d["Open"]).abs()
        d["_body_avg"] = d["_body"].shift(1).rolling(cfg.body_avg_period).mean()
        d["_box_high"] = d["High"].shift(1).rolling(cfg.box_lookback_bars).max()
        d["_box_low"] = d["Low"].shift(1).rolling(cfg.box_lookback_bars).min()

        cur = d.iloc[-1]
        prev = d.iloc[-2]
        close = float(cur["Close"])
        open_ = float(cur["Open"])
        high = float(cur["High"])
        low = float(cur["Low"])
        ma_short = float(cur[short_col])
        ma_long = float(cur[long_col])

        slope_pos = len(d) - 1 - cfg.slope_lookback_bars
        long_slope_pct = _pct_change(ma_long, float(d[long_col].iloc[slope_pos]))
        short_slope_pct = _pct_change(ma_short, float(d[short_col].iloc[slope_pos]))
        price_above_long = close > ma_long
        price_above_short = close > ma_short
        long_up = pd.notna(long_slope_pct) and long_slope_pct > 0
        long_flat = pd.notna(long_slope_pct) and abs(long_slope_pct) <= cfg.flat_long_slope_abs_pct
        short_up = pd.notna(short_slope_pct) and short_slope_pct > 0
        bull_regime = price_above_long and long_up
        reversal_regime = price_above_long and long_flat and short_up
        trend_ok = bull_regime or reversal_regime

        bullish = close > open_
        bearish = close < open_
        body_avg = float(cur["_body_avg"]) if pd.notna(cur["_body_avg"]) else float("nan")
        long_bull_body = bool(bullish and body_avg > 0 and float(cur["_body"]) >= body_avg * cfg.long_body_ratio)
        long_bear_body = bool(bearish and body_avg > 0 and float(cur["_body"]) >= body_avg * cfg.long_body_ratio)
        upper_ma = max(ma_short, ma_long)
        lower_ma = min(ma_short, ma_long)
        detached_above = low > upper_ma
        detached_below = high < lower_ma

        prior_high = float(d["High"].shift(1).rolling(cfg.prior_high_lookback_bars).max().iloc[-1])
        prior_high_breakout = bool(bullish and pd.notna(prior_high) and close > prior_high)

        gap = (d[short_col] - d[long_col]).abs() / d[long_col].replace(0, np.nan) * 100.0
        recent_gap = gap.tail(cfg.squeeze_recent_bars).dropna()
        baseline_gap = gap.tail(cfg.squeeze_lookback_bars).dropna()
        min_recent_gap = float(recent_gap.min()) if not recent_gap.empty else float("nan")
        median_gap = float(baseline_gap.median()) if not baseline_gap.empty else float("nan")
        squeeze_compressed = bool(
            pd.notna(min_recent_gap) and pd.notna(median_gap)
            and min_recent_gap <= cfg.squeeze_gap_max_pct
            and (median_gap <= 0 or min_recent_gap <= median_gap * cfg.squeeze_compression_ratio)
        )
        look = d.iloc[-(cfg.squeeze_recent_bars + 1):-1]
        inside_recent = False
        if not look.empty:
            lo_band = look[[short_col, long_col]].min(axis=1)
            hi_band = look[[short_col, long_col]].max(axis=1)
            inside_recent = bool(((look["Close"] >= lo_band) & (look["Close"] <= hi_band)).any())
        breakout_confirmed = long_bull_body or detached_above or prior_high_breakout
        squeeze_breakout = bool(
            squeeze_compressed and inside_recent and close > upper_ma
            and breakout_confirmed and trend_ok
        )

        recent = d.tail(cfg.pullback_lookback_bars)
        recent_short = recent[short_col]
        touch_distance = (recent["Low"] - recent_short).abs() / recent_short.replace(0, np.nan) * 100.0
        recent_short_touch = bool((touch_distance <= cfg.ma_touch_tolerance_pct).any())
        previous_below_or_touch = bool(
            float(prev["Close"]) <= float(prev[short_col]) * (1 + cfg.ma_touch_tolerance_pct / 100.0)
        )
        pullback_reclaim = bool(
            trend_ok and short_up and price_above_short and bullish
            and recent_short_touch and previous_below_or_touch
        )
        strong_pullback_confirmation = bool(pullback_reclaim and long_bull_body and detached_above)

        close_short_cross = _cross_count(d["Close"], d[short_col], cfg.cross_lookback_bars)
        close_long_cross = _cross_count(d["Close"], d[long_col], cfg.cross_lookback_bars)
        ma_cross = _cross_count(d[short_col], d[long_col], cfg.cross_lookback_bars)
        cross_total = close_short_cross + close_long_cross + ma_cross
        sideways = cross_total >= cfg.sideways_cross_count

        box_high = float(cur["_box_high"])
        box_low = float(cur["_box_low"])
        box_breakout = bool(
            pd.notna(box_high)
            and float(prev["Close"]) <= box_high * (1 + cfg.box_breakout_buffer_pct / 100.0)
            and close > box_high * (1 + cfg.box_breakout_buffer_pct / 100.0)
            and bullish
            and (long_bull_body or detached_above)
            and trend_ok
        )

        retest_level = float("nan")
        retest_age = 0
        for age in range(cfg.box_retest_lookback_bars, 0, -1):
            idx = len(d) - 1 - age
            if idx < max(cfg.box_lookback_bars, cfg.long_ma_period) - 1:
                break
            r = d.iloc[idx]
            level = r["_box_high"]
            if pd.isna(level) or pd.isna(r[short_col]) or pd.isna(r[long_col]):
                continue
            r_bull = float(r["Close"]) > float(r["Open"])
            r_body_avg = float(r["_body_avg"]) if pd.notna(r["_body_avg"]) else float("nan")
            r_long_body = bool(r_bull and r_body_avg > 0 and float(r["_body"]) >= r_body_avg * cfg.long_body_ratio)
            r_detached = float(r["Low"]) > max(float(r[short_col]), float(r[long_col]))
            r_prev_close = float(d["Close"].iloc[idx - 1]) if idx > 0 else float("nan")
            if (
                r_bull
                and pd.notna(r_prev_close)
                and r_prev_close <= float(level) * (1 + cfg.box_breakout_buffer_pct / 100.0)
                and float(r["Close"]) > float(level) * (1 + cfg.box_breakout_buffer_pct / 100.0)
                and (r_long_body or r_detached)
            ):
                retest_level = float(level)
                retest_age = age
                break

        box_retest_hold = bool(
            pd.notna(retest_level)
            and low <= retest_level * (1 + cfg.box_retest_tolerance_pct / 100.0)
            and low >= retest_level * (1 - cfg.box_retest_max_break_pct / 100.0)
            and close >= retest_level
            and bullish
            and trend_ok
        )

        long_ma_breakdown = bool(close < ma_long and (long_bear_body or detached_below))
        ma20_distance_pct = _pct_change(close, ma_short)
        chase_risk = bool(pd.notna(ma20_distance_pct) and ma20_distance_pct > cfg.max_ma20_distance_pct)
        near_short_ma = bool(abs(ma20_distance_pct) <= cfg.ma_touch_tolerance_pct) if pd.notna(ma20_distance_pct) else False

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if price_above_long:
            score += 15; reasons.append(f"가격이 {cfg.long_ma_period}MA 위")
        else:
            warnings.append(f"가격이 {cfg.long_ma_period}MA 아래")
        if long_up:
            score += 15; reasons.append(f"{cfg.long_ma_period}MA 우상향")
        elif long_flat and short_up:
            score += 8; reasons.append(f"{cfg.long_ma_period}MA 수평권 + 단기 MA 상승 전환")
        else:
            warnings.append(f"{cfg.long_ma_period}MA 상승 방향 미확인")
        if ma_short > ma_long:
            score += 5; reasons.append("단기 MA가 장기 MA 위")
        if short_up:
            score += 5; reasons.append("단기 MA 우상향")

        if squeeze_compressed:
            score += 8; reasons.append("단기/장기 MA 스퀴즈 압축")
        if squeeze_breakout:
            score += 5; reasons.append("스퀴즈 상단 돌파(확정 전 WATCH setup)")

        if strong_pullback_confirmation:
            score += 15; reasons.append("강한 단기 MA 눌림 재돌파 확인")
        elif pullback_reclaim:
            score += 5; reasons.append("단기 MA 눌림 재돌파 setup")

        if box_breakout:
            score += 20; reasons.append("박스 상단 강한 돌파")
        elif prior_high_breakout:
            score += 10; reasons.append("직전 고점 몸통 돌파")

        if box_retest_hold:
            score += 10; reasons.append(f"과거 박스 돌파 {retest_age}봉 후 실제 재테스트 지지")
        if long_bull_body:
            score += 5; reasons.append("장대 양봉 확인")
        if detached_above:
            score += 5; reasons.append("캔들이 이동평균선 위로 완전 분리")
        if sideways:
            warnings.append(f"최근 반복 교차 {cross_total}회: 횡보 위험")
        else:
            score += 5; reasons.append("반복 교차 과다 없음")
        if chase_risk:
            warnings.append(f"단기 MA 대비 이격 과다: {ma20_distance_pct:.2f}%")
        else:
            score += 5; reasons.append("단기 MA 대비 추격 위험 낮음")
        score = min(100, int(score))

        timing_score = 0
        if box_breakout:
            timing_score += 55
        elif prior_high_breakout:
            timing_score += 40
        if box_retest_hold:
            timing_score += 45
        if strong_pullback_confirmation:
            timing_score += 50
        elif pullback_reclaim:
            timing_score += 20
        if squeeze_breakout:
            timing_score += 20
        if long_bull_body:
            timing_score += 10
        if detached_above:
            timing_score += 10
        timing_score = min(100, timing_score)

        prior_high_confirmed = bool(prior_high_breakout and (long_bull_body or detached_above))
        confirmed_trigger = box_breakout or box_retest_hold or strong_pullback_confirmation or prior_high_confirmed
        watch_setup = (
            squeeze_compressed or squeeze_breakout or pullback_reclaim
            or prior_high_breakout or box_retest_hold or near_short_ma
        )
        sideways_block = sideways and not (box_breakout or box_retest_hold)

        if long_ma_breakdown:
            status = "REJECTED"; primary = "LONG_MA_DECISIVE_BREAKDOWN"
        elif sideways_block:
            status = "REJECTED"; primary = "SIDEWAYS_NO_TRADE"
        elif (
            trend_ok and confirmed_trigger and not chase_risk
            and score >= cfg.confirmed_score
            and timing_score >= cfg.confirmed_timing_score
        ):
            if score >= cfg.strong_confirmed_score and timing_score >= cfg.strong_timing_score:
                status = "STRONG_CONFIRMED"
            else:
                status = "CONFIRMED"
            if box_retest_hold:
                primary = "BOX_RETEST_CONFIRMED"
            elif box_breakout:
                primary = "BOX_BREAKOUT"
            elif strong_pullback_confirmation:
                primary = "PULLBACK_STRONG_CONFIRMATION"
            else:
                primary = "PRIOR_HIGH_BREAKOUT"
        elif trend_ok and watch_setup and score >= cfg.watch_score:
            status = "WATCH"
            if squeeze_breakout:
                primary = "SQUEEZE_BREAKOUT_WATCH"
            elif pullback_reclaim:
                primary = "PULLBACK_RECLAIM_WATCH"
            elif squeeze_compressed:
                primary = "SQUEEZE_SETUP_WATCH"
            else:
                primary = "TREND_OK_WAIT_CONFIRMATION"
        else:
            status = "REJECTED"
            if not trend_ok:
                primary = "LONG_DIRECTION_NOT_CONFIRMED"
            elif chase_risk:
                primary = "CHASE_RISK"
            else:
                primary = "ENTRY_CONDITIONS_INCOMPLETE"

        metrics = {
            "Close": round(close, 4),
            f"MA{cfg.short_ma_period}": round(ma_short, 4),
            f"MA{cfg.long_ma_period}": round(ma_long, 4),
            "Long_MA_Slope_Pct": round(float(long_slope_pct), 4),
            "Short_MA_Slope_Pct": round(float(short_slope_pct), 4),
            "Bull_Regime": bull_regime,
            "Reversal_Regime": reversal_regime,
            "Squeeze_Compressed": squeeze_compressed,
            "Squeeze_Min_Gap_Pct": round(min_recent_gap, 4) if pd.notna(min_recent_gap) else None,
            "Squeeze_Breakout": squeeze_breakout,
            "Pullback_Reclaim": pullback_reclaim,
            "Strong_Pullback_Confirmation": strong_pullback_confirmation,
            "Prior_High": round(prior_high, 4) if pd.notna(prior_high) else None,
            "Prior_High_Breakout": prior_high_breakout,
            "Long_Bull_Body": long_bull_body,
            "Detached_Above_MA": detached_above,
            "Cross_Count": cross_total,
            "Sideways": sideways,
            "Box_High": round(box_high, 4) if pd.notna(box_high) else None,
            "Box_Low": round(box_low, 4) if pd.notna(box_low) else None,
            "Box_Breakout": box_breakout,
            "Box_Retest_Hold": box_retest_hold,
            "Box_Retest_Level": round(retest_level, 4) if pd.notna(retest_level) else None,
            "Box_Retest_Age_Bars": retest_age,
            "MA20_Distance_Pct": round(float(ma20_distance_pct), 4) if pd.notna(ma20_distance_pct) else None,
            "Chase_Risk": chase_risk,
            "Long_MA_Breakdown": long_ma_breakdown,
            "Stop_Entry_Candle_Low": round(low, 4),
            "Stop_Short_MA": round(ma_short, 4),
        }
        return MAAnalysisResult(
            ticker=ticker, name=name, market=market,
            requested_date=requested_date, actual_date=actual_date,
            status=status, score=score, timing_score=timing_score,
            primary_signal=primary, reasons=reasons, warnings=warnings,
            metrics=metrics,
        )
