from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

SearchPhase = Literal["confirmed", "strong"]


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    values: tuple[Any, ...]


class BaseThresholdAdapter(ABC):
    """Analyzer-specific contract for the shared threshold optimizer.

    The shared optimizer owns walk-forward splitting, grid search, objective
    scoring, stability/plateau analysis and report writing. Each Analyzer owns
    only the semantics of its thresholds and how a parameter set selects rows.
    """

    analyzer_name: str = "UNKNOWN"
    date_column: str = "scan_date"

    def __init__(self, phase: SearchPhase, analyzer_config: dict, confirmed_floor: dict | None = None):
        self.phase = phase
        self.analyzer_config = analyzer_config
        self.confirmed_floor = confirmed_floor or {}

    @abstractmethod
    def parameter_space(self, optimizer_config: dict) -> dict[str, list[Any]]:
        raise NotImplementedError

    @abstractmethod
    def current_parameters(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def required_columns(self) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    def select_mask(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        raise NotImplementedError

    def validate_parameters(self, params: dict[str, Any]) -> bool:
        return True

    @abstractmethod
    def export_config(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a YAML-serializable partial Analyzer config."""
        raise NotImplementedError

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        missing = sorted(self.required_columns() - set(df.columns))
        if missing:
            raise ValueError(
                f"{self.analyzer_name}/{self.phase}: optimizer input missing columns: {missing}"
            )
        if self.date_column not in df.columns:
            raise ValueError(f"date column missing: {self.date_column}")

    def parameter_distance(self, params: dict[str, Any], space: dict[str, list[Any]]) -> float:
        """Normalized L1 distance from the currently configured thresholds."""
        current = self.current_parameters()
        distances: list[float] = []
        for name, values in space.items():
            if name not in params or name not in current or not values:
                continue
            value = params[name]
            base = current[name]
            if all(isinstance(v, (int, float)) for v in values) and isinstance(value, (int, float)) and isinstance(base, (int, float)):
                lo, hi = float(min(values)), float(max(values))
                span = hi - lo
                distances.append(0.0 if span <= 0 else abs(float(value) - float(base)) / span)
            else:
                distances.append(0.0 if value == base else 1.0)
        return float(sum(distances) / len(distances)) if distances else 0.0
