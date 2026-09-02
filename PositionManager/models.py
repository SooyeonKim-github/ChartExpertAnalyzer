from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Fill:
    stage: int
    date: str
    price: float
    weight: float
    quantity: float


@dataclass
class BacktestResult:
    signal_date: str
    analyzer: str
    ticker: str
    name: str
    status: str
    score: Optional[float]
    timing_score: Optional[float]

    stage1_date: str = ""
    stage1_price: Optional[float] = None
    stage2_date: str = ""
    stage2_price: Optional[float] = None
    stage3_date: str = ""
    stage3_price: Optional[float] = None

    stage2_target: Optional[float] = None
    initial_stop_price: Optional[float] = None
    invested_weight: float = 0.0
    avg_entry_price: Optional[float] = None

    exit_date: str = ""
    exit_price: Optional[float] = None
    exit_reason: str = ""
    trade_status: str = ""

    position_return_pct: Optional[float] = None
    strategy_return_on_planned_capital_pct: Optional[float] = None
    baseline_d20_pct: Optional[float] = None
    alpha_vs_baseline_d20_pct: Optional[float] = None

    bars_held: Optional[int] = None
    max_favorable_excursion_pct: Optional[float] = None
    max_adverse_excursion_pct: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)
