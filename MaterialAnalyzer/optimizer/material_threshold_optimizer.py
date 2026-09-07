from __future__ import annotations

"""Compatibility shim for the retired return-based optimizer.

MaterialAnalyzer's purpose is catalyst collection/quality classification, so forward-return
optimization is intentionally disabled. Import MaterialQualityOptimizer for new code.
"""

from .material_quality_optimizer import MaterialQualityOptimizer, QualityOptimizerRunResult


class MaterialThresholdOptimizer(MaterialQualityOptimizer):
    """Deprecated alias kept so existing imports do not silently run return optimization."""


OptimizerRunResult = QualityOptimizerRunResult

__all__ = ["MaterialThresholdOptimizer", "OptimizerRunResult"]
