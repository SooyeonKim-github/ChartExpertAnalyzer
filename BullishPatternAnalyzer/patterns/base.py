from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd
from core.models import PatternDetection


class BasePatternDetector(ABC):
    @abstractmethod
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        raise NotImplementedError


def clamp_score(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)
