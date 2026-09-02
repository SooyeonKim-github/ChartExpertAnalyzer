from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    planned_capital: float = 10_000_000.0

    # V3: small starter position first, then add only on strength confirmation.
    stage1_weight: float = 0.20
    stage2_weight: float = 0.30
    stage3_weight: float = 0.50

    # Stage 1 is no longer delayed by CHASE_RISK / EXPIRED logic.
    # Every CONFIRMED signal starts with a small position on the next trading-day open.
    use_daily_entry_gate: bool = False

    # Legacy daily-entry score thresholds are kept only for diagnostics / compatibility.
    entry_buy_score: float = 80.0
    entry_wait_rebound_score: float = 65.0
    entry_cancel_score: float = 50.0

    # Hard-cancel rules used to block additional buying after structure deterioration.
    hard_cancel_distribution_drop_pct: float = 0.04
    hard_cancel_volume_ratio: float = 1.50

    # V3 scale-in rules: no averaging-down limit order.
    # Additional buys require bullish rebound / breakout confirmation at the close,
    # then execute on the following trading-day open.
    stage2_window_bars: int = 10
    stage3_window_bars: int = 10
    stage2_min_daily_score: float = 75.0
    stage3_min_daily_score: float = 75.0

    structural_lookback_bars: int = 10
    structural_stop_buffer_pct: float = 0.01
    max_stop_pct: float = 0.08

    trailing_activate_pct: float = 0.10
    trailing_stop_pct: float = 0.07
    max_holding_bars: int = 20

    slippage_bps: float = 5.0

    def validate(self) -> None:
        weight_sum = self.stage1_weight + self.stage2_weight + self.stage3_weight
        if abs(weight_sum - 1.0) > 1e-9:
            raise ValueError(f"stage weights must sum to 1.0, got {weight_sum}")
        if self.planned_capital <= 0:
            raise ValueError("planned_capital must be positive")
        if not (0 <= self.entry_cancel_score <= self.entry_wait_rebound_score <= self.entry_buy_score <= 100):
            raise ValueError("entry score thresholds must satisfy cancel <= wait <= buy <= 100")
        if not (0 <= self.stage2_min_daily_score <= 100):
            raise ValueError("stage2_min_daily_score must be between 0 and 100")
        if not (0 <= self.stage3_min_daily_score <= 100):
            raise ValueError("stage3_min_daily_score must be between 0 and 100")
        for name in (
            "stage1_weight", "stage2_weight", "stage3_weight",
            "max_stop_pct", "trailing_activate_pct", "trailing_stop_pct",
            "hard_cancel_distribution_drop_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.hard_cancel_volume_ratio < 0:
            raise ValueError("hard_cancel_volume_ratio must be non-negative")


DEFAULT_CONFIG = StrategyConfig()
