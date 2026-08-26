from __future__ import annotations

import logging
import pandas as pd
from core.models import PatternDetection
from patterns.bull_flag import BullFlagDetector
from patterns.reversal import FallingWedgeDetector, InverseHeadShouldersDetector, WPatternDetector
from patterns.triangles import AscendingTriangleDetector, SymmetricalTriangleDetector


logger = logging.getLogger(__name__)


class PatternEngine:
    def __init__(self) -> None:
        self.detectors = [AscendingTriangleDetector(), SymmetricalTriangleDetector(), BullFlagDetector(), FallingWedgeDetector(), WPatternDetector(), InverseHeadShouldersDetector()]

    def detect_all(self, df: pd.DataFrame) -> list[PatternDetection]:
        results = []
        for detector in self.detectors:
            try:
                result = detector.detect(df)
            except Exception as exc:
                logger.warning("%s failed: %s", detector.__class__.__name__, exc)
                result = None
            if result is not None:
                results.append(result)
        return results
