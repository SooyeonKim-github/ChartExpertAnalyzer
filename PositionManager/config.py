from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    planned_capital: float = 10_000_000.0

    stage1_weight: float = 0.20
    stage2_weight: float = 0.30
    stage3_weight: float = 0.50

    # Daily entry gate: D0 CONFIRMED -> evaluate D+1 close onward -> buy next open only when READY_BUY.
    use_daily_entry_gate: bool = True
    entry_watch_bars: int = 10
    entry_buy_score: float = 80.0
    entry_wait_rebound_score: float = 65.0
    entry_cancel_score: float = 50.0
    min_heat_score_for_entry: float = 5.0

    # Chase / overheat controls.
    chase_signal_gain_pct: float = 0.05
    chase_extreme_signal_gain_pct: float = 0.08
    chase_ma20_distance_pct: float = 0.08

    # Hard cancel rules before the first entry.
    hard_cancel_daily_drop_pct: float = 0.05
    hard_cancel_distribution_drop_pct: float = 0.04
    hard_cancel_volume_ratio: float = 1.50
    hard_cancel_gap_down_pct: float = 0.05

    # Scale-in rules after Stage 1.
    stage2_pullback_pct: float = 0.025
    stage2_window_bars: int = 10
    stage3_window_bars: int = 10
    stage2_min_daily_score: float = 65.0
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
        if self.entry_watch_bars < 1:
            raise ValueError("entry_watch_bars must be at least 1")
        if not (0 <= self.entry_cancel_score <= self.entry_wait_rebound_score <= self.entry_buy_score <= 100):
            raise ValueError("entry score thresholds must satisfy cancel <= wait <= buy <= 100")
        for name in (
            "stage1_weight", "stage2_weight", "stage3_weight",
            "stage2_pullback_pct", "max_stop_pct",
            "trailing_activate_pct", "trailing_stop_pct",
            "chase_signal_gain_pct", "chase_extreme_signal_gain_pct",
            "chase_ma20_distance_pct", "hard_cancel_daily_drop_pct",
            "hard_cancel_distribution_drop_pct", "hard_cancel_gap_down_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


DEFAULT_CONFIG = StrategyConfig()
