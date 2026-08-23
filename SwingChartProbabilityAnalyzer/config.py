from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "cache"
RESULT_DIR = PROJECT_ROOT / "results"
INFO_EXCEL_PATH = PROJECT_ROOT / "KOSPI_Info.xlsx"


@dataclass(frozen=True)
class StrategyConfig:
    """영상 규칙을 수치화한 파라미터.

    중요: 아래 숫자는 영상에 없는 새로운 지표가 아니라, 영상의 정성적 표현
    (전고점/전저점, 추세선 하단, 쌍바닥, 이평선 밀집, 거래량 급증 등)을
    코드로 판정하기 위한 허용오차/관찰기간이다.
    """

    # 최소 히스토리
    min_history_bars: int = 140
    history_calendar_days: int = 520

    # 스윙 고점/저점: 양옆 pivot_window 봉보다 높거나 낮아야 확정
    pivot_window: int = 3
    structure_lookback_bars: int = 120

    # 영상의 '중기 상승 + 단기 조정'
    pullback_lookback_bars: int = 20
    min_pullback_pct: float = 0.03
    max_pullback_pct: float = 0.30
    prior_low_break_tolerance: float = 0.03

    # 고점 2개 연결 + 평행 이동한 상승 채널
    channel_min_high_gap: int = 8
    channel_max_high_gap: int = 70
    channel_min_width_pct: float = 0.05
    channel_max_width_pct: float = 0.45
    channel_cover_tolerance: float = 0.08
    channel_min_coverage: float = 0.72
    channel_touch_tolerance: float = 0.14
    cheap_zone_position: float = 0.35
    recent_lower_touch_position: float = 0.28
    recent_lower_touch_bars: int = 15
    max_entry_channel_position: float = 0.58

    # 쌍바닥 / higher-low
    double_bottom_lookback_bars: int = 45
    double_bottom_min_gap: int = 5
    double_bottom_max_gap: int = 30
    double_bottom_price_tolerance: float = 0.06
    higher_low_tolerance: float = 0.03

    # 영상의 '이평선들이 밀집', '이평선 넘어서는 것', '5선 지지'
    ma_periods: tuple[int, ...] = (5, 20, 60)
    ma_cluster_max_spread: float = 0.065
    ma_reclaim_lookback_bars: int = 7
    ma5_hold_tolerance: float = 0.025

    # 바닥권 거래량 급증 + 양봉 기준봉
    volume_avg_period: int = 20
    volume_surge_ratio: float = 1.8
    reference_candle_lookback_bars: int = 20
    reference_low_tolerance: float = 0.03

    # 영상에서 예시로 언급한 3~5% 손절 중 보수적으로 3% 사용
    stop_buffer_pct: float = 0.03

    # 신호 판정
    confirmed_score: int = 75
    watch_score: int = 58

    # 과거 동일 규칙의 성공률 계산
    backtest_horizon_bars: int = 20
    calibration_min_samples: int = 12
    calibration_step_bars: int = 3
    calibration_cooldown_bars: int = 10

    def to_dict(self) -> dict:
        data = asdict(self)
        data["ma_periods"] = ",".join(map(str, self.ma_periods))
        return data


DEFAULT_CONFIG = StrategyConfig()
