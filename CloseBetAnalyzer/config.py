from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CloseBetConfig:
    """Initial V1 thresholds.

    These are implementation defaults for validation, not fixed rules from the lectures.
    Keep them configurable and re-estimate them with range backtests before treating them
    as production thresholds.
    """

    confirmed_score: float = 72.0
    strong_confirmed_score: float = 82.0
    watch_score: float = 62.0

    min_stock_rs: float = 50.0
    strong_stock_rs: float = 65.0
    min_sector_score: float = 50.0
    strong_sector_score: float = 65.0
    downtrend_min_stock_rs: float = 65.0

    near_high_pct: float = 0.08
    overextended_ma20_pct: float = 0.12

    # Manual buy-day guide. The analyzer does NOT ingest intraday charts in V1.
    buy_day_soft_drop_pct: float = 0.03
    buy_day_hard_cancel_pct: float = 0.05
    buy_day_preferred_max_gain_pct: float = 0.05
    buy_day_chase_pct: float = 0.08
    guide_support_buffer_pct: float = 0.01

    market_weight: float = 0.15
    sector_weight: float = 0.20
    stock_rs_weight: float = 0.20
    liquidity_weight: float = 0.15
    structure_weight: float = 0.25
    volume_weight: float = 0.05

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


DEFAULT_CONFIG = CloseBetConfig()
