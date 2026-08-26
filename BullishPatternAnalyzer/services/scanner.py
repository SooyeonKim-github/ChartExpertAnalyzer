from __future__ import annotations

import pandas as pd
from config import MARKET, SCORE, UNIVERSE
from core.analysis import market_context
from core.models import Candidate, MarketRegime, PatternState
from core.pattern_engine import PatternEngine
from core.scorer import BullishPatternScorer
from data.data_provider import PyKrxDataProvider
from data.universe_service import UniverseService


class BullishPatternScanner:
    def __init__(self, provider: PyKrxDataProvider | None = None) -> None:
        self.provider = provider or PyKrxDataProvider()
        self.universe = UniverseService(self.provider)
        self.engine = PatternEngine()
        self.scorer = BullishPatternScorer()

    def scan(self, as_of: str, top_n: int | None = None) -> list[Candidate]:
        universe = self.universe.build(as_of, top_n)
        results = []
        end = pd.Timestamp(as_of)
        start = end - pd.Timedelta(days=UNIVERSE.history_calendar_days)
        regimes = {}
        for market in universe["market"].dropna().unique().tolist():
            idx_ticker = MARKET.index_tickers.get(str(market))
            idx_df = self.provider.index_ohlcv(idx_ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")) if idx_ticker else pd.DataFrame()
            regimes[str(market)] = market_context(idx_df)
        for row in universe.itertuples(index=False):
            results.extend(self._scan_ticker(as_of, row.ticker, row.name, row.market, regimes.get(row.market, MarketRegime.UNKNOWN)))
        return sorted(results, key=lambda x: (x.selection_score, x.timing_score), reverse=True)

    def _scan_ticker(self, as_of: str, ticker: str, name: str, market: str, regime: MarketRegime) -> list[Candidate]:
        end = pd.Timestamp(as_of)
        start = end - pd.Timedelta(days=UNIVERSE.history_calendar_days)
        try:
            df = self.provider.stock_ohlcv(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        except Exception:
            return []
        if len(df) < UNIVERSE.min_history_bars:
            return []

        out = []
        for det in self.engine.detect_all(df):
            scored = self.scorer.score(df, det, regime)
            if scored["selection_score"] < SCORE.watch_selection_min and det.state == PatternState.FORMING:
                continue
            br = scored["breakout"]
            vol = scored["volume"]
            candle = scored["candle"]
            mom = scored["momentum"]
            ret = scored["retest"]
            risk = scored["risk"]
            reasons = list(det.reasons)
            if br["confirmed"] and vol["filter_pass"]:
                reasons.append("종가 돌파 + 거래량 필터 통과")
            elif br["confirmed"]:
                reasons.append("가격 돌파했으나 거래량 필터 미통과")
            if vol["pre_breakout_contraction"]:
                reasons.append("돌파 전 거래량 수축")
            if vol["ratio"] >= 1.3:
                reasons.append(f"20일 평균 대비 거래량 {vol['ratio']:.2f}배")
            if candle["signal"] != "NONE":
                reasons.append(f"캔들={candle['signal']}")
            if scored["divergence"]:
                reasons.append("RSI 상승 다이버전스")
            if scored["mfi_divergence"]:
                reasons.append("MFI 상승 다이버전스")
            if candle["bearish_warning"]:
                reasons.append("고점 매도압력형 캔들 경고")

            metrics = {
                **det.metrics,
                "price_breakout_confirmed": br["confirmed"],
                "breakout_volume_ratio": vol["ratio"],
                "volume_filter_pass": vol["filter_pass"],
                "pre_breakout_volume_contraction": vol["pre_breakout_contraction"],
                "pre_breakout_volume_contraction_ratio": vol["contraction_ratio"],
                "volume_oscillator_pct": vol["volume_oscillator_pct"],
                "volume_oscillator_positive": vol["volume_oscillator_positive"],
                "volume_oscillator_rising": vol["volume_oscillator_rising"],
                "bearish_volume_divergence": vol["bearish_volume_divergence"],
                "mfi14": mom["mfi14"],
                "mfi_bullish_divergence": scored["mfi_divergence"],
                "above_ma200": mom["above_ma200"],
                **{f"candle_{k}": v for k, v in candle.items() if k not in {"score", "signal"}},
                "chase_atr": risk["chase_atr"],
                "stop_distance_pct": risk["stop_distance_pct"],
            }
            out.append(Candidate(
                date=end.strftime("%Y%m%d"), ticker=ticker, name=name, market=market,
                pattern_type=det.pattern_type, pattern_category=det.category, pattern_state=scored["state"],
                structure_score=det.structure_score, breakout_score=br["score"], volume_score=vol["score"],
                candle_score=candle["score"], momentum_score=mom["score"], retest_score=ret["score"],
                selection_score=scored["selection_score"], timing_score=scored["timing_score"],
                volume_filter_pass=vol["filter_pass"], candle_signal=candle["signal"],
                chase_risk=risk["chase"], entry_risk=risk["entry"], market_regime=regime,
                breakout_level=det.breakout_level, support_level=det.support_level, stop_level=det.stop_level,
                current_price=float(df.iloc[-1]["close"]), breakout_price=det.breakout_level if br["confirmed"] else None,
                volume_ratio=vol["ratio"], distance_from_breakout_pct=br["distance_pct"],
                bullish_divergence=scored["divergence"], retest_valid=ret["valid"],
                signal_reason="; ".join(reasons),
                risk_reason=f"추격위험={risk['chase'].value}, 손절거리위험={risk['entry'].value}, 시장={regime.value}",
                metrics=metrics,
            ))
        return out
