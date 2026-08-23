from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

@dataclass
class Signal:
    name: str
    score: float
    category: str
    direction: str = 'neutral'
    reason: str = ''
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AnalysisResult:
    ticker: str
    asof: str
    close: float
    total_score: float
    grade: str
    action: str
    market_regime: str
    confluence_score: float = 50.0
    relative_strength_score: float = 50.0
    relative_strength_grade: str = 'C'
    leader_score: float = 50.0
    relative_strength_weight: float = 0.0
    relative_strength_metrics: Dict[str, Any] = field(default_factory=dict)
    technical_score: float = 50.0
    technical_grade: str = 'C'
    timing_score: float = 50.0
    timing_grade: str = 'C'
    risk_score: float = 50.0
    risk_level: str = '보통'
    chase_risk: str = '보통'
    entry_status: str = '관찰'
    technical_components: Dict[str, float] = field(default_factory=dict)
    timing_components: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    signals: List[Signal] = field(default_factory=list)
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    stop_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    entry_plan: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out['signals'] = [asdict(s) for s in self.signals]
        return out
