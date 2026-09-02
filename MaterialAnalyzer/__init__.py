"""MaterialAnalyzer.

Collection, future schedule extraction, and explainable V1 schedule analysis are kept
as separate layers so each stage can be backtested and upgraded independently.
"""

from .collector import MaterialCollector
from .collectors.schedule import ScheduleCollector
from .config import DEFAULT_CONFIG, MaterialCollectorConfig
from .schedule_analysis import ScheduleAnalysisEngine
from .schedule_models import ScheduleItem

__all__ = [
    "MaterialCollector",
    "ScheduleCollector",
    "ScheduleAnalysisEngine",
    "ScheduleItem",
    "MaterialCollectorConfig",
    "DEFAULT_CONFIG",
]
