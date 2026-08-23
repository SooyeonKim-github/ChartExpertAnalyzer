from __future__ import annotations

import math
import pandas as pd

from config import StrategyConfig
from core.models import AnalysisResult
from core.probability import pattern_key, score_band


def _safe_round(value: float, digits: int = 3) -> float:
    if value is None or not math.isfinite(float(value)):
        return float("nan")
    return round(float(value), digits)


def _window_performance(
    df_full: pd.DataFrame,
    signal_end_pos: int,
    entry: float,
    window_bars: int,
    available: int,
) -> dict[str, object]:
    """지정 거래봉 구간의 MFE/MAE/최대·최소 종가수익률을 계산한다."""
    used = min(int(window_bars), int(available))
    out: dict[str, object] = {
        f"Forward_Complete_{window_bars}D": int(available >= window_bars),
    }
    if used <= 0:
        out.update(
            {
                f"Max_Close_Return_{window_bars}D_Pct": float("nan"),
                f"Min_Close_Return_{window_bars}D_Pct": float("nan"),
                f"MFE_{window_bars}D_Pct": float("nan"),
                f"MAE_{window_bars}D_Pct": float("nan"),
                f"Positive_D{window_bars}": float("nan"),
            }
        )
        return out

    future = df_full.iloc[signal_end_pos + 1 : signal_end_pos + used + 1]
    close_returns = (future["Close"] / entry - 1.0) * 100.0
    high_returns = (future["High"] / entry - 1.0) * 100.0
    low_returns = (future["Low"] / entry - 1.0) * 100.0
    point_return = (
        _safe_round((float(future["Close"].iloc[window_bars - 1]) / entry - 1.0) * 100.0)
        if available >= window_bars
        else float("nan")
    )
    out.update(
        {
            f"Max_Close_Return_{window_bars}D_Pct": _safe_round(float(close_returns.max())),
            f"Min_Close_Return_{window_bars}D_Pct": _safe_round(float(close_returns.min())),
            f"MFE_{window_bars}D_Pct": _safe_round(float(high_returns.max())),
            f"MAE_{window_bars}D_Pct": _safe_round(float(low_returns.min())),
            f"Positive_D{window_bars}": (
                int(point_return > 0) if pd.notna(point_return) else float("nan")
            ),
        }
    )
    return out


def evaluate_forward_returns(
    df_full: pd.DataFrame,
    signal_end_pos: int,
    horizon_bars: int = 20,
) -> dict:
    """신호 발생일 종가 대비 향후 N거래일의 실제 성과를 계산한다.

    중요:
    - 미래 데이터는 신호 판정에 절대 사용하지 않고 사후 성과평가에만 사용한다.
    - D+1 ... D+N은 달력일이 아니라 해당 종목의 다음 거래봉 기준이다.
    - horizon이 60이어도 D+20 값은 실제 20번째 거래봉 값으로 유지한다.
    - 종목 거래정지/데이터 부족 등으로 N개 봉이 없으면 존재하는 구간만 채우고 나머지는 NaN이다.
    """
    if df_full is None or df_full.empty or signal_end_pos < 0 or signal_end_pos >= len(df_full):
        return {}

    horizon_bars = max(1, int(horizon_bars))
    entry = float(df_full["Close"].iloc[signal_end_pos])
    available = max(0, min(horizon_bars, len(df_full) - signal_end_pos - 1))

    out: dict[str, object] = {
        "Forward_Entry_Close": entry,
        "Forward_Available_Bars": available,
        "Forward_Horizon_Bars": horizon_bars,
        f"Forward_Complete_{horizon_bars}D": int(available >= horizon_bars),
    }

    for d in range(1, horizon_bars + 1):
        ret_col = f"D+{d}_Close_Return_Pct"
        close_col = f"D+{d}_Close"
        date_col = f"D+{d}_Date"
        if d <= available:
            pos = signal_end_pos + d
            close = float(df_full["Close"].iloc[pos])
            out[ret_col] = _safe_round((close / entry - 1.0) * 100.0)
            out[close_col] = close
            out[date_col] = df_full.index[pos].strftime("%Y-%m-%d")
        else:
            out[ret_col] = float("nan")
            out[close_col] = float("nan")
            out[date_col] = ""

    if available > 0:
        out["Forward_Last_Date"] = df_full.index[signal_end_pos + available].strftime("%Y-%m-%d")
    else:
        out["Forward_Last_Date"] = ""

    milestones = [d for d in (5, 10, 20, 40, 60) if d <= horizon_bars]
    if horizon_bars not in milestones:
        milestones.append(horizon_bars)
    for day in sorted(set(milestones)):
        out.update(_window_performance(df_full, signal_end_pos, entry, day, available))

    if "Forward_Complete_20D" not in out:
        out["Forward_Complete_20D"] = int(available >= 20)
        out["MFE_20D_Pct"] = float("nan")
        out["MAE_20D_Pct"] = float("nan")
        out["Max_Close_Return_20D_Pct"] = float("nan")
        out["Min_Close_Return_20D_Pct"] = float("nan")
        out["Positive_D20"] = float("nan")

    return out


def evaluate_signal(df_full: pd.DataFrame, signal_end_pos: int, result: AnalysisResult, cfg: StrategyConfig) -> dict | None:
    if result.channel is None or result.status == "REJECTED":
        return None
    ch = result.channel
    end = min(len(df_full) - 1, signal_end_pos + cfg.backtest_horizon_bars)
    if end <= signal_end_pos:
        return None

    entry = float(df_full["Close"].iloc[signal_end_pos])
    prior_high = float(result.metrics.get("Prior_High_Target", entry))
    swing_stop_base = float(result.metrics.get("Stop_Price", entry * (1 - cfg.stop_buffer_pct)))

    mid_at_signal = ch.mid(signal_end_pos)
    upper_at_signal = ch.upper(signal_end_pos)
    valid_mid = mid_at_signal > entry
    valid_prior = prior_high > entry
    valid_upper = upper_at_signal > entry

    hit_mid = False
    hit_prior = False
    hit_upper = False
    stop_hit = False
    first_event = "TIMEOUT"
    exit_pos = end

    for i in range(signal_end_pos + 1, end + 1):
        low = float(df_full["Low"].iloc[i])
        high = float(df_full["High"].iloc[i])
        dynamic_channel_stop = ch.lower(i) * (1.0 - cfg.stop_buffer_pct)
        stop = max(dynamic_channel_stop, swing_stop_base)
        if low <= stop:
            stop_hit = True
            first_event = "STOP"
            exit_pos = i
            break
        if valid_mid and high >= ch.mid(i):
            hit_mid = True
        if valid_prior and high >= prior_high:
            hit_prior = True
        if valid_upper and high >= ch.upper(i):
            hit_upper = True
        if hit_upper:
            first_event = "UPPER"
            exit_pos = i
            break

    future = df_full.iloc[signal_end_pos + 1 : end + 1]
    mfe = (float(future["High"].max()) / entry - 1.0) * 100 if not future.empty else 0.0
    mae = (float(future["Low"].min()) / entry - 1.0) * 100 if not future.empty else 0.0

    row = {
        "Signal_Date": df_full.index[signal_end_pos].strftime("%Y-%m-%d"),
        "Ticker": result.ticker,
        "Name": result.name,
        "Status": result.status,
        "Score": result.score,
        "Score_Band": score_band(result.score),
        "Pattern_Key": pattern_key(result.metrics),
        "Entry": entry,
        "Hit_Mid_Before_Stop": int(hit_mid) if valid_mid else float("nan"),
        "Hit_PriorHigh_Before_Stop": int(hit_prior) if valid_prior else float("nan"),
        "Hit_Upper_Before_Stop": int(hit_upper) if valid_upper else float("nan"),
        "Stop_Hit": int(stop_hit),
        "First_Event": first_event,
        "MFE_Pct": round(mfe, 3),
        "MAE_Pct": round(mae, 3),
        "Exit_Date": df_full.index[exit_pos].strftime("%Y-%m-%d"),
    }
    row.update(evaluate_forward_returns(df_full, signal_end_pos, cfg.backtest_horizon_bars))
    return row
