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
        self.provider = provider or PyKrxDataProvider(); self.universe = UniverseService(self.provider); self.engine = PatternEngine(); self.scorer = BullishPatternScorer()

    def scan(self, as_of: str, top_n: int | None = None) -> list[Candidate]:
        universe = self.universe.build(as_of, top_n); results = []; end = pd.Timestamp(as_of); start = end - pd.Timedelta(days=UNIVERSE.history_calendar_days); regimes = {}
        for market in universe["market"].dropna().unique().tolist():
            idx_ticker = MARKET.index_tickers.get(str(market)); idx_df = self.provider.index_ohlcv(idx_ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d")) if idx_ticker else pd.DataFrame(); regimes[str(market)] = market_context(idx_df)
        for row in universe.itertuples(index=False): results.extend(self._scan_ticker(as_of, row.ticker, row.name, row.market, regimes.get(row.market, MarketRegime.UNKNOWN)))
        return sorted(results, key=lambda x: (x.selection_score, x.timing_score), reverse=True)

    def _scan_ticker(self, as_of: str, ticker: str, name: str, market: str, regime: MarketRegime) -> list[Candidate]:
        end = pd.Timestamp(as_of); start = end - pd.Timedelta(days=UNIVERSE.history_calendar_days)
        try: df = self.provider.stock_ohlcv(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        except Exception: return []
        if len(df) < UNIVERSE.min_history_bars: return []
        out = []
        for det in self.engine.detect_all(df):
            scored = self.scorer.score(df, det, regime)
            if scored["selection_score"] < SCORE.watch_selection_min and det.state == PatternState.FORMING: continue
            br, vol, mom, ret, risk = scored["breakout"], scored["volume"], scored["momentum"], scored["retest"], scored["risk"]; reasons = list(det.reasons)
            if br["confirmed"]: reasons.append("종가 기준 돌파 확인")
            if vol["ratio"] >= 1.3: reasons.append(f"20일 평균 대비 거래량 {vol['ratio']:.2f}배")
            if scored["divergence"]: reasons.append("상승 다이버전스 확인")
            out.append(Candidate(date=end.strftime("%Y%m%d"), ticker=ticker, name=name, market=market, pattern_type=det.pattern_type, pattern_category=det.category, pattern_state=scored["state"], structure_score=det.structure_score, breakout_score=br["score"], volume_score=vol["score"], momentum_score=mom["score"], retest_score=ret["score"], selection_score=scored["selection_score"], timing_score=scored["timing_score"], chase_risk=risk["chase"], entry_risk=risk["entry"], market_regime=regime, breakout_level=det.breakout_level, support_level=det.support_level, stop_level=det.stop_level, current_price=float(df.iloc[-1]["close"]), breakout_price=det.breakout_level if br["confirmed"] else None, volume_ratio=vol["ratio"], distance_from_breakout_pct=br["distance_pct"], bullish_divergence=scored["divergence"], retest_valid=ret["valid"], signal_reason="; ".join(reasons), risk_reason=f"추격위험={risk['chase'].value}, 손절거리위험={risk['entry'].value}, 시장={regime.value}", metrics={**det.metrics, "chase_atr": risk["chase_atr"], "stop_distance_pct": risk["stop_distance_pct"]}))
        return out
