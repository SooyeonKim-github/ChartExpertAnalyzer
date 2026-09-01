from __future__ import annotations

import math
import pandas as pd

from classifier import classify
from config import PullbackConfig
from impulse_detector import detect_impulse
from indicators import build_indicators
from market_context import analyze_market_context
from models import PullbackAnalysisResult
from pullback_detector import detect_pullback
from risk import build_risk_plan
from scoring import score_setup
from support_detector import detect_support


def _round(v, n=4):
    try:
        return round(float(v), n) if math.isfinite(float(v)) else None
    except Exception:
        return None


def _pullback_type(pullback, support) -> str:
    name = support.nearest_name or ""
    if pullback.period_correction:
        return "PERIOD_CORRECTION"
    if name in {"MA5", "MA10", "MA20", "MA60"}:
        return f"{name}_PULLBACK"
    if support.bb_support:
        return "TREND_BB"
    if name == "BREAKOUT_LEVEL":
        return "BREAKOUT_RETEST"
    return "SURGE_PULLBACK"


class PullbackAnalyzer:
    """Independent lecture-derived pullback analyzer.

    Score measures setup quality; Timing_Score measures whether today is actionable.
    """

    def __init__(self, cfg: PullbackConfig) -> None:
        self.cfg = cfg

    def _insufficient_result(self, ticker: str, name: str, market: str, requested_date: str,
                             stock_df: pd.DataFrame) -> PullbackAnalysisResult:
        actual_date = stock_df.index[-1].strftime("%Y-%m-%d") if len(stock_df) else ""
        return PullbackAnalysisResult(
            ticker=ticker, name=name, market=market, requested_date=requested_date,
            actual_date=actual_date, status="REJECT", score=0, timing_score=0,
            primary_signal="INSUFFICIENT_HISTORY", pullback_type="NONE",
            warnings=[f"히스토리 부족: {len(stock_df)} < {self.cfg.min_history_bars}"],
        )

    def analyze(self, ticker: str, name: str, market: str, requested_date: str,
                stock_df: pd.DataFrame, market_df: pd.DataFrame | None = None) -> PullbackAnalysisResult:
        """Analyze one date using the normal path used by screen/explain commands."""
        if len(stock_df) < self.cfg.min_history_bars:
            return self._insufficient_result(ticker, name, market, requested_date, stock_df)
        d = build_indicators(stock_df, self.cfg)
        return self._analyze_ready(ticker, name, market, requested_date, stock_df, d, market_df)

    def analyze_precomputed(self, ticker: str, name: str, market: str, requested_date: str,
                            stock_df: pd.DataFrame, indicator_df: pd.DataFrame,
                            market_df: pd.DataFrame | None = None) -> PullbackAnalysisResult:
        """Analyze using indicators already calculated for the full ticker history.

        Rolling indicators are backward-looking, so slicing a once-precomputed frame at a
        historical position is equivalent to recalculating the same indicators for every
        prefix. This path is used by range backtests to avoid repeated MA/ATR/BB work.
        """
        if len(stock_df) < self.cfg.min_history_bars:
            return self._insufficient_result(ticker, name, market, requested_date, stock_df)
        if len(indicator_df) != len(stock_df) or not indicator_df.index.equals(stock_df.index):
            raise ValueError("stock_df와 indicator_df의 길이/인덱스가 일치해야 합니다.")
        return self._analyze_ready(ticker, name, market, requested_date, stock_df, indicator_df, market_df)

    def _analyze_ready(self, ticker: str, name: str, market: str, requested_date: str,
                       stock_df: pd.DataFrame, d: pd.DataFrame,
                       market_df: pd.DataFrame | None = None) -> PullbackAnalysisResult:
        actual_date = stock_df.index[-1].strftime("%Y-%m-%d") if len(stock_df) else ""
        impulse = detect_impulse(d, self.cfg)
        pullback = detect_pullback(d, impulse, self.cfg)
        support = detect_support(d, impulse, pullback, self.cfg)
        market_ctx = analyze_market_context(stock_df, market_df)
        risk = build_risk_plan(d, pullback, support, self.cfg)
        components, score, timing, flags, reasons, warnings = score_setup(
            d, impulse, pullback, support, market_ctx, risk, self.cfg
        )
        status, primary, class_warnings = classify(
            d, impulse, pullback, support, components, score, timing, flags, risk, self.cfg
        )
        warnings.extend(class_warnings)
        ptype = _pullback_type(pullback, support) if pullback.available else "NONE"

        cur = d.iloc[-1]
        metrics = {
            "Close": _round(cur["Close"]),
            "Impulse_Date": impulse.date,
            "Impulse_Base_Date": impulse.base_date,
            "Impulse_Return_Pct": _round(impulse.return_pct),
            "Impulse_Volume_Ratio": _round(impulse.volume_ratio),
            "Impulse_Body_ATR": _round(impulse.body_atr),
            "Impulse_Breakout": impulse.breakout,
            "Impulse_High": _round(impulse.high_price),
            "Impulse_Base": _round(impulse.base_price),
            "Breakout_Level": _round(impulse.breakout_level),
            "Pullback_Sequence": pullback.sequence,
            "Pullback_Bars": pullback.bars,
            "Pullback_Depth_Pct": _round(pullback.depth_pct),
            "Pullback_Retracement_Ratio": _round(pullback.retracement_ratio),
            "Current_Drawdown_From_Impulse_Pct": _round(pullback.current_drawdown_pct),
            "Correction_Type": pullback.correction_type,
            "Period_Correction": pullback.period_correction,
            "Higher_Low": pullback.higher_low,
            "Midpoint_Broken": pullback.midpoint_broken,
            "ATR_Contraction": pullback.atr_contraction,
            "Range_Contraction": pullback.range_contraction,
            "Price_Stopping": pullback.price_stopping,
            "Pullback_Volume_Ratio_Impulse": _round(pullback.volume_ratio_impulse),
            "Pullback_Volume_Ratio_20": _round(pullback.volume_ratio_20),
            "High_Volume_Breakdown": pullback.high_volume_breakdown,
            "Nearest_Support": support.nearest_name,
            "Nearest_Support_Level": _round(support.nearest_level),
            "Support_Distance_Pct": _round(support.distance_pct),
            "Support_Confluence_Count": support.confluence_count,
            "Support_Touch_Count": support.touch_count,
            "Support_Held": support.support_held,
            "BB_Support": support.bb_support,
            "Bullish_Reversal": flags.get("bullish_reversal", False),
            "Minor_High_Breakout": flags.get("minor_high_breakout", False),
            "MA_Reclaim": flags.get("ma_reclaim", False),
            "Confirmation_Volume_Ratio": _round(flags.get("confirmation_volume_ratio")),
            "Local_High": _round(flags.get("local_high")),
            "Market_Regime": market_ctx.regime,
            "Market_Ret20": _round(market_ctx.market_ret20),
            "Market_Ret60": _round(market_ctx.market_ret60),
            "RS20": _round(market_ctx.rs20),
            "RS60": _round(market_ctx.rs60),
            "RS_Score": _round(market_ctx.rs_score),
            "Stop_Price": _round(risk.get("stop_price")),
            "Stop_Distance_Pct": _round(risk.get("stop_distance_pct")),
            "MA20_Extension_Pct": _round(risk.get("ma20_extension_pct")),
            "Chase_Risk": risk.get("chase_risk", False),
            "Catalyst_Available": False,
            "Sector_Context_Available": False,
            "Adverse_News_Flag": "UNKNOWN",
        }
        for p in self.cfg.ma_periods:
            metrics[f"MA{p}"] = _round(cur[f"MA{p}"])
            if pd.notna(cur[f"MA{p}"]) and float(cur[f"MA{p}"]) != 0:
                metrics[f"Distance_MA{p}_Pct"] = _round((float(cur["Close"]) / float(cur[f"MA{p}"]) - 1.0) * 100.0)

        return PullbackAnalysisResult(
            ticker=ticker, name=name, market=market, requested_date=requested_date,
            actual_date=actual_date, status=status, score=score, timing_score=timing,
            primary_signal=primary, pullback_type=ptype, reasons=reasons, warnings=warnings,
            component_scores=components, metrics=metrics,
        )
