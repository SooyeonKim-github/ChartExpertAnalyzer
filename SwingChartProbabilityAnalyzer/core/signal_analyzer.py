from __future__ import annotations

import math
import pandas as pd

from config import StrategyConfig
from core.bottom_analyzer import analyze_double_bottom, analyze_moving_averages
from core.channel_analyzer import build_best_rising_channel, channel_metrics
from core.market_structure import analyze_market_structure
from core.models import AnalysisResult
from core.pivots import find_confirmed_pivots
from core.probability import EmpiricalProbabilityModel
from core.volume_analyzer import analyze_bottom_volume_and_reference


class SwingSignalAnalyzer:
    def __init__(self, cfg: StrategyConfig, probability_model: EmpiricalProbabilityModel | None = None):
        self.cfg = cfg
        self.probability_model = probability_model

    def analyze(self, ticker: str, name: str, target_date: str, df: pd.DataFrame) -> AnalysisResult:
        if len(df) < self.cfg.min_history_bars:
            return AnalysisResult(ticker, name, target_date, str(df.index[-1].date()) if len(df) else "", "REJECTED", 0,
                                  "INSUFFICIENT_HISTORY", warnings=[f"히스토리 부족 {len(df)}봉"])
        highs, lows = find_confirmed_pivots(df, self.cfg.pivot_window)
        structure = analyze_market_structure(df, highs, lows, self.cfg)
        channel = build_best_rising_channel(df, highs, lows, self.cfg)
        actual_date = df.index[-1].strftime("%Y-%m-%d")

        if not structure["valid"]:
            return AnalysisResult(ticker, name, target_date, actual_date, "REJECTED", 0, "NO_SWING_STRUCTURE",
                                  warnings=["확정 스윙 고점/저점 부족"])
        if channel is None:
            return AnalysisResult(ticker, name, target_date, actual_date, "REJECTED", 0, "NO_RISING_CHANNEL",
                                  warnings=["영상 방식의 상승 평행채널을 안정적으로 구성하지 못함"])

        cm = channel_metrics(df, channel, self.cfg)
        db = analyze_double_bottom(df, lows, channel, self.cfg)
        ma = analyze_moving_averages(df, self.cfg)
        vol = analyze_bottom_volume_and_reference(df, channel, self.cfg)

        score = 0
        reasons: list[str] = []
        warnings: list[str] = []

        if structure["uptrend"]:
            score += 20; reasons.append("중기 Higher High + Higher Low")
        else:
            warnings.append("중기 상승 구조 미확인")
        if structure["pullback"] and structure["prior_low_held"]:
            score += 10; reasons.append("상승추세 안의 단기 조정 + 전저점 유지")
        elif not structure["prior_low_held"]:
            warnings.append("최근 스윙 저점 이탈 위험")

        # 채널 품질 자체
        if channel.coverage >= self.cfg.channel_min_coverage:
            score += 10; reasons.append(f"상승 평행채널 유효(커버리지 {channel.coverage:.0%})")
        if cm["recent_lower_touch"]:
            score += 10; reasons.append("최근 추세 하단(싼 구간) 접촉")
        if cm["near_lower"]:
            score += 5; reasons.append("현재도 채널 하단권")

        if db["exists"]:
            score += 5; reasons.append("추세 하단 부근 쌍바닥/Higher-Low 형태")
        if db["confirmed"]:
            score += 5; reasons.append("쌍바닥 넥라인 돌파 확인")

        if ma["clustered"]:
            score += 8; reasons.append("이동평균선 밀집")
        if ma["reclaimed"]:
            score += 8; reasons.append("이동평균선 재돌파")

        if vol["bottom_volume_surge"]:
            score += 10; reasons.append("추세 바닥권 거래량 급증 양봉")
        if vol["reference_low_held"]:
            score += 4; reasons.append("거래량 기준봉 저가 지지")
        if vol["reference_high_break"]:
            score += 5; reasons.append("거래량 기준봉 고가 돌파")
        elif vol["bullish_turn"]:
            score += 3; reasons.append("기준봉 지지 후 재상승 전환")
        if ma["ma5_hold"] and ma["reclaimed"]:
            score += 2; reasons.append("재상승 후 5일선 지지")

        score = min(100, score)
        hard_fail = (not structure["uptrend"] or not structure["prior_low_held"] or cm["breakdown"])
        confirmation = db["confirmed"] or vol["reference_high_break"] or vol["bullish_turn"] or ma["reclaimed"]
        not_chasing = cm["position"] <= self.cfg.max_entry_channel_position

        confirmed_conditions = (
            score >= self.cfg.confirmed_score
            and cm["recent_lower_touch"]
            and confirmation
            and not_chasing
        )

        if hard_fail:
            status = "REJECTED"
            primary = "TREND_BROKEN_OR_NOT_UPTREND"
        elif confirmed_conditions and score >= self.cfg.strong_confirmed_score:
            status = "STRONG_CONFIRMED"
            primary = "D10_STRONG_LOWER_CHANNEL_CONFIRMED_REVERSAL"
        elif confirmed_conditions:
            status = "CONFIRMED"
            primary = "LOWER_CHANNEL_CONFIRMED_REVERSAL"
        elif score >= self.cfg.watch_score and cm["recent_lower_touch"]:
            status = "WATCH"
            primary = "LOWER_CHANNEL_WATCH"
        else:
            status = "REJECTED"
            primary = "CONDITIONS_INCOMPLETE"

        pos = len(df)-1
        prior_high = structure["last_high"].price if structure["last_high"] else float("nan")
        current = float(df["Close"].iloc[-1])
        stop = max(channel.lower(pos)*(1.0-self.cfg.stop_buffer_pct),
                   structure["last_low"].price*(1.0-self.cfg.stop_buffer_pct))
        metrics = {
            "Close": round(current, 4),
            "Uptrend_HH_HL": structure["uptrend"],
            "Pullback_Pct": round(structure["pullback_pct"]*100, 2),
            "Prior_Low_Held": structure["prior_low_held"],
            "Channel_Coverage": round(channel.coverage, 4),
            "Channel_Position": round(cm["position"], 4),
            "Recent_Lower_Touch": cm["recent_lower_touch"],
            "Channel_Lower": round(cm["lower"], 4),
            "Channel_Mid": round(cm["mid"], 4),
            "Prior_High_Target": round(prior_high, 4),
            "Channel_Upper": round(cm["upper"], 4),
            "Stop_Price": round(stop, 4),
            "Room_To_Mid_Pct": round(cm["room_to_mid_pct"]*100, 2),
            "Room_To_Upper_Pct": round(cm["room_to_upper_pct"]*100, 2),
            "Double_Bottom": db["exists"],
            "Double_Bottom_Confirmed": db["confirmed"],
            "MA_Clustered": ma["clustered"],
            "MA_Spread_Pct": round(ma["spread"]*100, 2) if math.isfinite(ma["spread"]) else None,
            "MA_Reclaimed": ma["reclaimed"],
            "MA5_Held": ma["ma5_hold"],
            "Bottom_Volume_Surge": vol["bottom_volume_surge"],
            "Reference_Date": vol["reference_date"],
            "Reference_Low_Held": vol["reference_low_held"],
            "Reference_High_Break": vol["reference_high_break"],
            "Reference_Volume_Ratio": round(vol["reference_volume_ratio"], 2) if pd.notna(vol["reference_volume_ratio"]) else None,
        }
        probs = self.probability_model.predict(score, status, metrics) if self.probability_model else {}
        return AnalysisResult(ticker, name, target_date, actual_date, status, score, primary, reasons, warnings, metrics, probs, channel)
