"""MaterialAnalyzer V1.

The first version starts from material collection and future schedule extraction.
Scoring and market-confirmation logic remain outside the collector layer.
"""

from .collector import MaterialCollector
from .collectors.schedule import ScheduleCollector
from .config import DEFAULT_CONFIG, MaterialCollectorConfig
from .schedule_models import ScheduleItem

__all__ = [
    "MaterialCollector",
    "ScheduleCollector",
    "ScheduleItem",
    "MaterialCollectorConfig",
    "DEFAULT_CONFIG",
]
