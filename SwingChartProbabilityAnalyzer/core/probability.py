from __future__ import annotations

from pathlib import Path
import pandas as pd

from config import StrategyConfig


def score_band(score: int) -> str:
    if score < 58: return "0-57"
    if score < 65: return "58-64"
    if score < 75: return "65-74"
    if score < 85: return "75-84"
    if score < 95: return "85-94"
    return "95-100"


def pattern_key(metrics: dict) -> str:
    """영상에 등장하는 확인요소만으로 패턴 서명을 만든다."""
    pos = metrics.get("Channel_Position")
    try:
        pos = float(pos)
    except (TypeError, ValueError):
        pos = 9.0
    if pos <= 0.35:
        pos_bucket = "LOW"
    elif pos <= 0.58:
        pos_bucket = "LOWMID"
    else:
        pos_bucket = "HIGH"
    bits = [
        f"POS={pos_bucket}",
        f"DB={int(bool(metrics.get('Double_Bottom_Confirmed')))}",
        f"MAC={int(bool(metrics.get('MA_Clustered')))}",
        f"MAR={int(bool(metrics.get('MA_Reclaimed')))}",
        f"VOL={int(bool(metrics.get('Bottom_Volume_Surge')))}",
        f"RLH={int(bool(metrics.get('Reference_Low_Held')))}",
        f"RHB={int(bool(metrics.get('Reference_High_Break')))}",
    ]
    return ";".join(bits)


class EmpiricalProbabilityModel:
    """같은 영상 규칙의 과거 신호가 목표를 손절보다 먼저 맞힌 비율."""

    def __init__(self, calibration_path: str | Path | None, cfg: StrategyConfig):
        self.cfg = cfg
        self.table = pd.DataFrame()
        if calibration_path:
            path = Path(calibration_path)
            if path.exists():
                self.table = pd.read_csv(path)

    def _status_candidates(self, status: str) -> list[str]:
        # 기존 calibration 파일에는 STRONG_CONFIRMED가 없을 수 있으므로
        # 동일한 CONFIRMED 모집단을 fallback으로 사용한다.
        if status == "STRONG_CONFIRMED":
            return ["STRONG_CONFIRMED", "CONFIRMED"]
        return [status]

    def _estimate(self, score: int, status: str, pkey: str, target_col: str) -> tuple[float | None, int, str]:
        if self.table.empty or target_col not in self.table.columns:
            return None, 0, "NO_CALIBRATION"

        status_candidates = self._status_candidates(status)

        # 1) 현재 영상 패턴 서명이 정확히 같은 과거 표본
        if "Pattern_Key" in self.table.columns:
            for candidate_status in status_candidates:
                sub = self.table[(self.table["Pattern_Key"] == pkey) & (self.table["Status"] == candidate_status)]
                vals = pd.to_numeric(sub[target_col], errors="coerce").dropna()
                if len(vals) >= self.cfg.calibration_min_samples:
                    wins=float(vals.sum()); n=len(vals)
                    source = "EXACT_PATTERN" if candidate_status == status else "CONFIRMED_EXACT_PATTERN_FALLBACK"
                    return (wins+1)/(n+2), n, source

        # 2) 같은 Status + Score band
        band = score_band(score)
        for candidate_status in status_candidates:
            sub = self.table[(self.table["Score_Band"] == band) & (self.table["Status"] == candidate_status)]
            vals = pd.to_numeric(sub[target_col], errors="coerce").dropna()
            if len(vals) >= self.cfg.calibration_min_samples:
                wins=float(vals.sum()); n=len(vals)
                source = "STATUS_SCORE_BAND" if candidate_status == status else "CONFIRMED_SCORE_BAND_FALLBACK"
                return (wins+1)/(n+2), n, source

        # 3) 같은 Status 전체. STRONG은 필요 시 기존 CONFIRMED 전체를 fallback으로 사용한다.
        last_n = 0
        for candidate_status in status_candidates:
            sub = self.table[self.table["Status"] == candidate_status]
            vals = pd.to_numeric(sub[target_col], errors="coerce").dropna()
            last_n = len(vals)
            if len(vals) >= self.cfg.calibration_min_samples:
                wins=float(vals.sum()); n=len(vals)
                source = "STATUS_FALLBACK" if candidate_status == status else "CONFIRMED_STATUS_FALLBACK"
                return (wins+1)/(n+2), n, source
        return None, last_n, "INSUFFICIENT_SAMPLE"

    def predict(self, score: int, status: str, metrics: dict) -> dict:
        pkey = pattern_key(metrics)
        output = {"Pattern_Key": pkey}
        mapping = {
            "Prob_Mid_Before_Stop": "Hit_Mid_Before_Stop",
            "Prob_PriorHigh_Before_Stop": "Hit_PriorHigh_Before_Stop",
            "Prob_Upper_Before_Stop": "Hit_Upper_Before_Stop",
        }
        sample_counts=[]; sources=[]
        for out_col, src in mapping.items():
            p,n,source=self._estimate(score,status,pkey,src)
            output[out_col]=round(p*100,1) if p is not None else None
            sample_counts.append(n); sources.append(source)
        output["Probability_Sample_Count"] = max(sample_counts) if sample_counts else 0
        output["Probability_Source"] = sources[0] if sources and len(set(sources)) == 1 else "/".join(sorted(set(sources)))
        return output
