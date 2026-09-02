from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BuyDayGuide:
    reference_close: float
    preferred_low: float
    preferred_high: float
    hold_level: float
    cancel_below: float
    chase_above: float
    buy_if: str
    wait_if: str
    skip_if: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CloseBetResult:
    actual_date: str
    ticker: str
    name: str
    market: str
    status: str
    score: float
    market_regime: str
    market_score: float
    sector_name: str
    sector_score: float
    sector_rank: float | None
    stock_rs_score: float
    liquidity_score: float
    source_rank: int | None
    structure_score: float
    volume_score: float
    close: float
    ma5: float | None
    ma20: float | None
    distance_60d_high_pct: float | None
    nearest_support: float | None
    nearest_resistance: float | None
    relative_volume: float | None
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    guide: BuyDayGuide | None = None

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        guide = row.pop("guide", None) or {}
        row["reasons"] = " | ".join(self.reasons)
        row["risks"] = " | ".join(self.risks)
        for key, value in guide.items():
            row[f"guide_{key}"] = value
        return row
