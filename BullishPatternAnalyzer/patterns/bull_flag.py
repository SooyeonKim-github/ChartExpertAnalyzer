from __future__ import annotations

import numpy as np
import pandas as pd
from config import PATTERN
from core.analysis import breakout_analysis
from core.models import PatternCategory, PatternDetection, PatternState, PatternType
from patterns.base import BasePatternDetector, clamp_score


class BullFlagDetector(BasePatternDetector):
    def detect(self, df: pd.DataFrame) -> PatternDetection | None:
        d = df.tail(PATTERN.bull_flag_lookback); need = PATTERN.bull_flag_pole_days + PATTERN.bull_flag_flag_days + 1
        if len(d) < need: return None
        flag = d.tail(PATTERN.bull_flag_flag_days); pole = d.iloc[-(PATTERN.bull_flag_flag_days + PATTERN.bull_flag_pole_days):-PATTERN.bull_flag_flag_days]
        pole_return = float(pole["close"].iloc[-1] / pole["close"].iloc[0] - 1.0)
        if pole_return < PATTERN.bull_flag_min_pole_return_pct: return None
        pole_high = float(pole["high"].max()); flag_low = float(flag["low"].min()); pullback = max(0.0, 1 - flag_low / pole_high)
        if pullback > PATTERN.bull_flag_max_pullback_pct: return None
        slope = float(np.polyfit(np.arange(len(flag)), flag["close"].to_numpy(float), 1)[0]); normalized_slope = slope / float(flag["close"].mean())
        if normalized_slope > 0.006: return None
        pole_vol = float(pole["volume"].mean()); flag_vol = float(flag["volume"].mean()); vol_ratio = flag_vol / pole_vol if pole_vol > 0 else np.nan
        resistance = float(flag["high"].iloc[:-1].max()); support = flag_low; br = breakout_analysis(df, resistance); vol_contract = np.isfinite(vol_ratio) and vol_ratio <= PATTERN.bull_flag_volume_contraction_ratio; structure = 55 + 25 * min(1.0, pole_return / 0.20) + (20 if vol_contract else 5); state = PatternState.BREAKOUT_CONFIRMED if br["confirmed"] else PatternState.WATCH
        return PatternDetection(PatternType.BULL_FLAG, PatternCategory.CONTINUATION, state, clamp_score(structure), resistance, support, support, metrics={"pole_return_pct": pole_return, "pullback_pct": pullback, "flag_to_pole_volume_ratio": None if not np.isfinite(vol_ratio) else vol_ratio, "flag_normalized_slope": normalized_slope}, reasons=["선행 급등(pole)", "조정 구간(flag)", "조정 중 거래량 감소", "상단 돌파 시 추세 지속 확인"])
