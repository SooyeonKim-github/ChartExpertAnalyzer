from __future__ import annotations

import math

import pandas as pd

STAGE_1 = "STAGE_1"
STAGE_2 = "STAGE_2"
STAGE_3 = "STAGE_3"
STAGE_4 = "STAGE_4"
INSUFFICIENT = "INSUFFICIENT"


def add_stage_labels(
    df: pd.DataFrame,
    *,
    slope_threshold_pct: float = 0.30,
) -> pd.DataFrame:
    """Classify the lecture's 4-stage cycle without look-ahead.

    Active lecture-core gate:
      - Stage 2: close > MA150 and MA150 slope > 0
      - Stage 4: close < MA150 and MA150 slope < 0

    `slope_threshold_pct` is intentionally NOT an active filter. It is an
    experimental threshold recorded for later range/ablation backtests.

    Stage 1/3 use the most recent definitive Stage 4/2 to preserve cycle
    context. This transition heuristic is an implementation choice and should
    be validated separately.
    """
    required = {"close", "ma150", "ma150_slope_pct"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing stage input columns: {sorted(missing)}")
    if slope_threshold_pct < 0:
        raise ValueError("slope_threshold_pct must be non-negative")

    out = df.copy()
    stages: list[str] = []
    reasons: list[str] = []
    strict_passes: list[bool] = []
    last_definitive: str | None = None

    for _, row in out.iterrows():
        close = row.get("close")
        ma150 = row.get("ma150")
        slope = row.get("ma150_slope_pct")

        if (
            close is None
            or ma150 is None
            or slope is None
            or pd.isna(close)
            or pd.isna(ma150)
            or pd.isna(slope)
            or not math.isfinite(float(close))
            or not math.isfinite(float(ma150))
            or not math.isfinite(float(slope))
        ):
            stages.append(INSUFFICIENT)
            reasons.append("MA150 또는 MA150 기울기 계산 데이터 부족")
            strict_passes.append(False)
            continue

        close_f = float(close)
        ma150_f = float(ma150)
        slope_f = float(slope)
        strict_passes.append(
            (close_f > ma150_f and slope_f >= slope_threshold_pct)
            or (close_f < ma150_f and slope_f <= -slope_threshold_pct)
        )

        if close_f > ma150_f and slope_f > 0:
            stage = STAGE_2
            reason = "LECTURE_CORE: 종가가 MA150 위이고 MA150 기울기가 상승"
            last_definitive = STAGE_2
        elif close_f < ma150_f and slope_f < 0:
            stage = STAGE_4
            reason = "LECTURE_CORE: 종가가 MA150 아래이고 MA150 기울기가 하락"
            last_definitive = STAGE_4
        elif last_definitive == STAGE_2:
            stage = STAGE_3
            reason = "IMPLEMENTATION: 최근 확정 Stage 2 이후 전환/횡보 구간"
        elif last_definitive == STAGE_4:
            stage = STAGE_1
            reason = "IMPLEMENTATION: 최근 확정 Stage 4 이후 전환/횡보 구간"
        else:
            if close_f >= ma150_f:
                stage = STAGE_3
                reason = "IMPLEMENTATION: 과거 확정 Stage 없음; MA150 위 비확정 구간"
            else:
                stage = STAGE_1
                reason = "IMPLEMENTATION: 과거 확정 Stage 없음; MA150 아래 비확정 구간"

        stages.append(stage)
        reasons.append(reason)

    out["stage"] = stages
    out["stage_reason"] = reasons
    out["trend_eligible"] = out["stage"].eq(STAGE_2)
    out["stage_core_pass"] = out["trend_eligible"]
    out["stage_experimental_slope_pass"] = strict_passes
    return out


def latest_stage_snapshot(
    df: pd.DataFrame,
    *,
    slope_threshold_pct: float = 0.30,
) -> dict:
    labeled = add_stage_labels(df, slope_threshold_pct=slope_threshold_pct)
    if labeled.empty:
        raise ValueError("Cannot classify an empty OHLCV frame")
    row = labeled.iloc[-1]
    return {
        "stage": str(row["stage"]),
        "stage_reason": str(row["stage_reason"]),
        "trend_eligible": bool(row["trend_eligible"]),
        "stage_core_pass": bool(row["stage_core_pass"]),
        "stage_experimental_slope_pass": bool(row["stage_experimental_slope_pass"]),
    }
