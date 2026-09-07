from .material_quality_optimizer import MaterialQualityOptimizer, QualityOptimizerRunResult

# Backward-compatible import name. New code should use MaterialQualityOptimizer.
MaterialThresholdOptimizer = MaterialQualityOptimizer
OptimizerRunResult = QualityOptimizerRunResult

__all__ = [
    "MaterialQualityOptimizer",
    "QualityOptimizerRunResult",
    "MaterialThresholdOptimizer",
    "OptimizerRunResult",
]
