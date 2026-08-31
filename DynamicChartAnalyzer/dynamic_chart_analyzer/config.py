from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for the staged RSI -> MACD -> Ichimoku strategy.

    Values explicitly stated in the lecture use the lecture defaults.  Values marked
    as mechanical rules are implementation choices needed to make qualitative chart
    language deterministic and backtestable.
    """

    # Capital / staged entry (lecture: 1 : 2 : 7)
    total_capital: float = 10_000_000.0
    stage1_ratio: float = 0.10
    stage2_ratio: float = 0.20
    stage3_ratio: float = 0.70

    # RSI (lecture defaults)
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    rsi_trend_midline: float = 50.0

    # MACD defaults
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Ichimoku defaults
    ichimoku_tenkan: int = 9
    ichimoku_kijun: int = 26
    ichimoku_senkou_b: int = 52
    ichimoku_displacement: int = 26

    # ATR / candle quality (mechanical definitions)
    atr_period: int = 14
    doji_body_ratio_max: float = 0.20
    strong_candle_body_atr_min: float = 0.55

    # Divergence pivot detection (mechanical definitions)
    divergence_lookback: int = 35
    divergence_pivot_window: int = 3
    divergence_min_rsi_delta: float = 2.0
    divergence_price_tolerance: float = 0.005

    # Cloud confirmation / retest (mechanical definitions)
    cloud_retest_tolerance: float = 0.01
    cloud_retest_lookback: int = 5
    thick_cloud_atr_ratio: float = 0.60

    # The lecture does not define how long a partial entry can wait forever.
    # These timeouts prevent stale Stage-1/Stage-2 signals from being completed much later.
    stage2_max_wait_bars: int = 15
    stage3_max_wait_bars: int = 20

    # Protective invalidation level based on a prior swing extreme.
    swing_stop_lookback: int = 10
    use_protective_stop: bool = True

    # Reference R-multiples shown in the lecture examples. They are reported, not used
    # as the main staged exit because the main strategy exits 1:2:7 on indicator reversal.
    long_reference_rr: float = 1.0
    short_reference_rr: float = 2.0

    # Optional account-risk cap from the lecture's later 2% rule.
    # OFF by default so 10,000,000 KRW becomes exactly 1m / 2m / 7m.
    use_two_percent_risk_cap: bool = False
    max_account_risk_ratio: float = 0.02

    def validate(self) -> None:
        ratios = self.stage1_ratio + self.stage2_ratio + self.stage3_ratio
        if abs(ratios - 1.0) > 1e-9:
            raise ValueError(f"Stage ratios must sum to 1.0, got {ratios}")
        if self.total_capital <= 0:
            raise ValueError("total_capital must be positive")
        if not (0 < self.max_account_risk_ratio < 1):
            raise ValueError("max_account_risk_ratio must be between 0 and 1")
        if self.divergence_pivot_window < 1:
            raise ValueError("divergence_pivot_window must be >= 1")
        if self.stage2_max_wait_bars < 1 or self.stage3_max_wait_bars < 1:
            raise ValueError("stage wait bars must be >= 1")
