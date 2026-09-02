"""MaterialAnalyzer V1.

The first version starts from material collection. Scoring and market-confirmation
logic are intentionally kept out of the collector layer.
"""

from .collector import MaterialCollector
from .config import DEFAULT_CONFIG, MaterialCollectorConfig

__all__ = ["MaterialCollector", "MaterialCollectorConfig", "DEFAULT_CONFIG"]
