from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloseBetConfig:
    """CloseBet V2 thresholds based on the first range-backtest review.

    These remain implementation thresholds, not immutable lecture rules.
    Catalyst and investor-flow factors are intentionally deferred.
    """

    # Shared by screen and range. Strengthening here strengthens both execution paths.
    confirmed_score: float = 76.0
    strong_confirmed_score: float = 80.0
    watch_score: float = 64.0

    min_stock_rs: float = 55.0
    strong_stock_rs: float = 65.0
    min_structure_score: float = 62.0
    strong_structure_score: float = 70.0

    min_sector_score: float = 50.0
    strong_sector_score: float = 65.0

    # Range/downtrend require stronger evidence than a normal/uptrend market.
    range_confirmed_score: float = 80.0
    range_min_stock_rs: float = 62.0
    downtrend_confirmed_score: float = 82.0
    downtrend_min_stock_rs: float = 70.0

    near_high_pct: float = 0.08
    max_confirmed_distance_60d_high_pct: float = 0.20
    overextended_ma20_pct: float = 0.12

    # Manual buy-day guide. The analyzer does NOT score the buy day's intraday chart.
    buy_day_soft_drop_pct: float = 0.03
    buy_day_hard_cancel_pct: float = 0.05
    buy_day_preferred_max_gain_pct: float = 0.05
    buy_day_chase_pct: float = 0.08
    guide_support_buffer_pct: float = 0.01

    # V2 de-emphasizes relative-volume bonus and puts more weight on RS/structure.
    market_weight: float = 0.15
    sector_weight: float = 0.15
    stock_rs_weight: float = 0.25
    liquidity_weight: float = 0.15
    structure_weight: float = 0.28
    volume_weight: float = 0.02

    def validate(self) -> None:
        weights = (
            self.market_weight
            + self.sector_weight
            + self.stock_rs_weight
            + self.liquidity_weight
            + self.structure_weight
            + self.volume_weight
        )
        if abs(weights - 1.0) > 1e-9:
            raise ValueError(f"CloseBet weights must sum to 1.0, got {weights}")
        if not (0 <= self.watch_score <= self.confirmed_score <= self.strong_confirmed_score <= 100):
            raise ValueError("score thresholds must satisfy watch <= confirmed <= strong <= 100")
        if not (0 <= self.buy_day_soft_drop_pct <= self.buy_day_hard_cancel_pct):
            raise ValueError("soft drop must be <= hard cancel")
        if not (0 <= self.buy_day_preferred_max_gain_pct <= self.buy_day_chase_pct):
            raise ValueError("preferred max gain must be <= chase threshold")
        if not (0 < self.near_high_pct <= self.max_confirmed_distance_60d_high_pct < 1):
            raise ValueError("high-distance thresholds are invalid")


DEFAULT_CONFIG = CloseBetConfig()
