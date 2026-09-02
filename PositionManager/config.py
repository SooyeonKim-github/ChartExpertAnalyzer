from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    planned_capital: float = 10_000_000.0

    stage1_weight: float = 0.20
    stage2_weight: float = 0.30
    stage3_weight: float = 0.50

    stage2_pullback_pct: float = 0.025
    stage2_window_bars: int = 10
    stage3_window_bars: int = 10

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
        for name in (
            "stage1_weight", "stage2_weight", "stage3_weight",
            "stage2_pullback_pct", "max_stop_pct",
            "trailing_activate_pct", "trailing_stop_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


DEFAULT_CONFIG = StrategyConfig()
