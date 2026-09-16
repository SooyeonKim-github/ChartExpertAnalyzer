from __future__ import annotations

"""Dynamic LONG V2.3 stage-aware quality model."""

import numpy as np
import pandas as pd

QUALITY_VERSION = "V2.3"


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _bool(df: pd.DataFrame, col: str, default: bool = False) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=bool)
    return df[col].fillna(default).astype(bool)


def _bool_points(series: pd.Series, points: float) -> np.ndarray:
    return series.fillna(False).astype(bool).to_numpy(dtype=float) * float(points)


def _market_context(market_score: pd.Series) -> np.ndarray:
    return np.select(
        [market_score.le(1).fillna(False), market_score.between(2, 3, inclusive="both").fillna(False), market_score.ge(4).fillna(False)],
        ["REVERSAL_ENV", "NEUTRAL_ENV", "TREND_ENV"],
        default="UNKNOWN",
    )


def _lecture_score(g: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    stage = _num(g, "stage").fillna(0)
    rsi_score = _bool_points(stage >= 1, 10) + _bool_points(_num(g, "rsi_rebound_strength") >= 5.0, 2) + _bool_points(_bool(g, "bullish_divergence_recent"), 3)
    macd_score = _bool_points(stage >= 2, 12) + _bool_points(_num(g, "macd_hist_slope") > 0, 4) + _bool_points(_num(g, "macd") < 0, 2) + _bool_points(_bool(g, "macd_hist_rising"), 2)
    macd_score = np.clip(macd_score, 0.0, 20.0)
    ichimoku_score = _bool_points(_bool(g, "tenkan_above_kijun"), 5) + _bool_points(_bool(g, "above_cloud"), 5) + _bool_points(_bool(g, "chikou_bullish"), 5) + _bool_points(~_bool(g, "doji_risk", default=True), 3) + _bool_points(stage >= 3, 7)
    ichimoku_score = np.clip(ichimoku_score, 0.0, 25.0)
    raw = np.clip(rsi_score + macd_score + ichimoku_score, 0.0, 60.0)
    return rsi_score, macd_score, ichimoku_score, raw / 60.0 * 100.0


def _rs_score(g: pd.DataFrame, cap: float) -> np.ndarray:
    p20, p60, rs20, rs60 = (_num(g, c) for c in ["rs_percentile_20", "rs_percentile_60", "rs_20", "rs_60"])
    p60_points = np.select([p60.ge(0.75).fillna(False), p60.ge(0.50).fillna(False), p60.ge(0.25).fillna(False)], [12.0, 9.0, 5.0], default=2.0)
    p20_points = np.select([p20.between(0.50, 0.75, inclusive="left").fillna(False), p20.ge(0.75).fillna(False), p20.ge(0.25).fillna(False)], [7.0, 5.0, 3.0], default=1.0)
    raw = p60_points + p20_points + np.where(rs60.isna(), 2.0, np.where(rs60 > 0, 6.0, 0.0)) + np.where(rs20.isna(), 1.5, np.where(rs20 > -0.03, 5.0, 0.0))
    return np.clip(raw * (float(cap) / 30.0), 0.0, float(cap))


def _trend_score(g: pd.DataFrame, cap: float = 20.0) -> np.ndarray:
    raw = _bool_points(_bool(g, "ma20_above_ma60"), 8) + _bool_points(_num(g, "ma60_slope") > 0, 6) + _bool_points(_num(g, "close_vs_ma60") > 0, 4) + _bool_points(_num(g, "ma20_slope") > 0, 2)
    return np.clip(raw * (float(cap) / 20.0), 0.0, float(cap))


def _stage1_scores(g: pd.DataFrame) -> dict[str, np.ndarray]:
    rs, trend = _rs_score(g, 30.0), _trend_score(g, 20.0)
    pullback, distance60, close_atr = _num(g, "pullback_depth"), _num(g, "distance_60d_high"), _num(g, "close_vs_atr")
    structure = np.clip(
        np.select([pullback.between(0.12, 0.20, inclusive="both").fillna(False), pullback.between(0.06, 0.12, inclusive="left").fillna(False), pullback.between(0.03, 0.06, inclusive="left").fillna(False), pullback.between(0.00, 0.03, inclusive="left").fillna(False), pullback.gt(0.20).fillna(False)], [12.0, 9.0, 6.0, 3.0, 2.0], default=0.0)
        + np.select([distance60.ge(-0.20).fillna(False), distance60.ge(-0.30).fillna(False)], [6.0, 3.0], default=0.0)
        + np.select([close_atr.abs().le(1.5).fillna(False), close_atr.abs().le(2.5).fillna(False)], [7.0, 3.0], default=0.0), 0.0, 25.0)
    contraction, vol5, vol20 = _num(g, "volume_contraction_10d"), _num(g, "volume_ratio_5"), _num(g, "volume_ratio_20")
    volume = np.clip(
        np.select([contraction.between(0.70, 0.95, inclusive="both").fillna(False), contraction.between(0.95, 1.05, inclusive="right").fillna(False), contraction.between(1.05, 1.20, inclusive="right").fillna(False)], [8.0, 5.0, 3.0], default=0.0)
        + np.select([vol5.between(0.70, 1.20, inclusive="both").fillna(False), vol5.between(1.20, 1.50, inclusive="right").fillna(False)], [4.0, 2.0], default=0.0)
        + np.where(vol20.le(1.10).fillna(False), 3.0, 0.0), 0.0, 15.0)
    rebound = _num(g, "rsi_rebound_strength")
    reversal = np.clip(np.select([rebound.ge(8).fillna(False), rebound.ge(5).fillna(False), rebound.ge(3).fillna(False)], [6.0, 4.0, 2.0], default=0.0) + _bool_points(_bool(g, "bullish_divergence_recent"), 4), 0.0, 10.0)
    total = np.clip(rs + trend + structure + volume + reversal, 0.0, 100.0)
    return {"rs": rs, "trend": trend, "structure": structure, "volume": volume, "reversal": reversal, "momentum": np.zeros(len(g)), "breakout": np.zeros(len(g)), "extension": np.zeros(len(g)), "total": total}


def _stage2_scores(g: pd.DataFrame) -> dict[str, np.ndarray]:
    rs, trend = _rs_score(g, 25.0), _trend_score(g, 20.0)
    rsi, rebound = _num(g, "rsi"), _num(g, "rsi_rebound_strength")
    momentum = np.clip(_bool_points(_num(g, "macd_hist_slope") > 0, 6) + _bool_points(_bool(g, "macd_hist_rising"), 4) + np.select([rebound.ge(8).fillna(False), rebound.ge(5).fillna(False), rebound.ge(3).fillna(False)], [5.0, 4.0, 2.0], default=0.0) + np.select([rsi.between(35, 60, inclusive="both").fillna(False), rsi.between(60, 70, inclusive="right").fillna(False)], [5.0, 3.0], default=1.0) + _bool_points(_bool(g, "bullish_divergence_recent"), 5), 0.0, 25.0)
    breakout_vol, vol5, contraction = _num(g, "breakout_volume_ratio"), _num(g, "volume_ratio_5"), _num(g, "volume_contraction_10d")
    volume = np.clip(np.select([breakout_vol.between(1.00, 1.50, inclusive="both").fillna(False), breakout_vol.between(0.80, 1.00, inclusive="left").fillna(False), breakout_vol.between(1.50, 2.00, inclusive="right").fillna(False)], [8.0, 5.0, 6.0], default=2.0) + np.where(vol5.ge(1.0).fillna(False), 4.0, 1.0) + np.where(contraction.le(1.10).fillna(False), 3.0, 0.0), 0.0, 15.0)
    pullback, distance60, close_atr = _num(g, "pullback_depth"), _num(g, "distance_60d_high"), _num(g, "close_vs_atr")
    structure = np.clip(np.select([pullback.between(0.06, 0.20, inclusive="both").fillna(False), pullback.between(0.03, 0.06, inclusive="left").fillna(False), pullback.gt(0.20).fillna(False)], [8.0, 5.0, 2.0], default=3.0) + np.where(distance60.ge(-0.20).fillna(False), 4.0, 1.0) + np.where(close_atr.abs().le(2.0).fillna(False), 3.0, 0.0), 0.0, 15.0)
    total = np.clip(rs + momentum + trend + volume + structure, 0.0, 100.0)
    return {"rs": rs, "trend": trend, "structure": structure, "volume": volume, "reversal": np.zeros(len(g)), "momentum": momentum, "breakout": np.zeros(len(g)), "extension": np.zeros(len(g)), "total": total}


def _stage3_scores(g: pd.DataFrame) -> dict[str, np.ndarray]:
    rs, trend = _rs_score(g, 30.0), _trend_score(g, 20.0)
    cloud_distance, cloud_thickness, tk_gap = _num(g, "cloud_distance"), _num(g, "cloud_thickness"), _num(g, "tenkan_kijun_gap")
    retest = _bool(g, "cloud_retest")
    breakout = np.clip(_bool_points(retest, 10) + np.select([cloud_distance.between(0.0, 0.03, inclusive="both").fillna(False), cloud_distance.between(0.03, 0.06, inclusive="right").fillna(False)], [7.0, 4.0], default=1.0) + np.select([tk_gap.between(0.0, 0.02, inclusive="both").fillna(False), tk_gap.between(0.02, 0.04, inclusive="right").fillna(False)], [4.0, 2.0], default=0.0) + np.where(cloud_thickness.le(0.05).fillna(False), 4.0, 2.0), 0.0, 25.0)
    breakout_vol, vol5, contraction = _num(g, "breakout_volume_ratio"), _num(g, "volume_ratio_5"), _num(g, "volume_contraction_10d")
    volume = np.clip(np.select([breakout_vol.between(1.00, 1.50, inclusive="both").fillna(False), breakout_vol.between(1.50, 2.00, inclusive="right").fillna(False), breakout_vol.between(0.80, 1.00, inclusive="left").fillna(False)], [8.0, 6.0, 4.0], default=1.0) + np.where(vol5.ge(1.0).fillna(False), 4.0, 1.0) + np.where(contraction.between(0.80, 1.20, inclusive="both").fillna(False), 3.0, 0.0), 0.0, 15.0)
    close_atr, distance20, rsi = _num(g, "close_vs_atr"), _num(g, "distance_20d_high"), _num(g, "rsi")
    extension = np.clip(np.select([close_atr.abs().le(1.5).fillna(False), close_atr.abs().le(2.5).fillna(False)], [5.0, 2.0], default=0.0) + np.select([distance20.between(-0.10, 0.01, inclusive="both").fillna(False), distance20.ge(-0.20).fillna(False)], [3.0, 1.0], default=0.0) + np.where(rsi.le(70).fillna(False), 2.0, 0.0), 0.0, 10.0)
    total = np.clip(rs + breakout + trend + volume + extension, 0.0, 100.0)
    return {"rs": rs, "trend": trend, "structure": np.zeros(len(g)), "volume": volume, "reversal": np.zeros(len(g)), "momentum": np.zeros(len(g)), "breakout": breakout, "extension": extension, "total": total}


def _risk_profile(g: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    stop, atr = _num(g, "stop_distance_pct"), _num(g, "atr_pct")
    chase = g.get("chase_risk", pd.Series("LOW", index=g.index)).fillna("LOW").astype(str).str.upper()
    levels, flags = [], []
    for idx in g.index:
        row_flags, level = [], 0
        s, a, c = stop.loc[idx], atr.loc[idx], chase.loc[idx]
        if pd.notna(s):
            if s > 0.15: level, row_flags = max(level, 2), row_flags + ["WIDE_STOP_GT15"]
            elif s > 0.08: level, row_flags = max(level, 1), row_flags + ["STOP_GT8"]
        if pd.notna(a):
            if a > 0.08: level, row_flags = max(level, 2), row_flags + ["ATR_GT8"]
            elif a > 0.05: level, row_flags = max(level, 1), row_flags + ["ATR_GT5"]
        if c == "HIGH": level, row_flags = max(level, 2), row_flags + ["CHASE_HIGH"]
        elif c == "MEDIUM": level, row_flags = max(level, 1), row_flags + ["CHASE_MEDIUM"]
        levels.append(["LOW", "MEDIUM", "HIGH"][level]); flags.append("|".join(row_flags))
    return np.asarray(levels, dtype=object), np.asarray(flags, dtype=object)


def _assign_setup_ids(out: pd.DataFrame, mask: pd.Series) -> None:
    out.loc[mask, "setup_id"], out.loc[mask, "setup_start_date"] = "", pd.NaT
    long_rows = out.loc[mask].copy()
    if long_rows.empty: return
    long_rows["signal_date"] = pd.to_datetime(long_rows["signal_date"], errors="coerce")
    long_rows = long_rows.sort_values(["ticker", "signal_date", "stage"], kind="stable")
    for ticker, group in long_rows.groupby("ticker", sort=False):
        counter, current_id, current_start = 0, None, pd.NaT
        for idx, row in group.iterrows():
            stage = int(pd.to_numeric(pd.Series([row.get("stage")]), errors="coerce").fillna(0).iloc[0])
            dt = pd.Timestamp(row["signal_date"]) if pd.notna(row["signal_date"]) else pd.NaT
            if stage == 1 or current_id is None:
                counter += 1; stamp = "UNKNOWN" if pd.isna(dt) else dt.strftime("%Y%m%d")
                current_id, current_start = f"{ticker}_{stamp}_{counter:03d}", dt
            out.at[idx, "setup_id"], out.at[idx, "setup_start_date"] = current_id, current_start


def score_long_events(events: pd.DataFrame, confirmed_score: float = 70.0, watch_score: float = 55.0, stage_thresholds: dict[int, tuple[float, float]] | None = None) -> pd.DataFrame:
    out = events.copy()
    out["quality_version"] = ""
    out["quality_stage"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    numeric_cols = ["lecture_rsi_score","lecture_macd_score","lecture_ichimoku_score","lecture_score","stage_quality_score","stage_rs_score","stage_trend_score","stage_structure_score","stage_volume_score","stage_reversal_score","stage_momentum_score","stage_breakout_score","stage_extension_score","quality_score","long_quality_score","quality_enhancement_score","quality_rs_score","quality_trend_score","quality_price_structure_score","quality_volume_score","quality_market_score","quality_risk_score","combined_score"]
    for col in numeric_cols: out[col] = np.nan
    out["stage_quality_label"], out["long_quality_label"] = "", ""
    out["market_context"], out["risk_level"], out["risk_flags"] = "UNKNOWN", "UNKNOWN", ""
    out["stage3_trigger_type"], out["stage3_deployable"], out["stage3_deploy_reason"] = "", False, ""
    out["daily_long_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["daily_stage_quality_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["setup_id"], out["setup_start_date"] = "", pd.NaT
    mask = out["side"].astype(str).eq("LONG")
    if not mask.any(): return out
    g = out.loc[mask].copy()
    rsi_l, macd_l, ichi_l, lecture = _lecture_score(g)
    out.loc[g.index, "lecture_rsi_score"] = np.round(rsi_l / 15.0 * 100.0, 2)
    out.loc[g.index, "lecture_macd_score"] = np.round(macd_l / 20.0 * 100.0, 2)
    out.loc[g.index, "lecture_ichimoku_score"] = np.round(ichi_l / 25.0 * 100.0, 2)
    out.loc[g.index, "lecture_score"] = np.round(lecture, 2)
    thresholds = {1:(float(confirmed_score),float(watch_score)),2:(float(confirmed_score),float(watch_score)),3:(float(confirmed_score),float(watch_score))}
    if stage_thresholds:
        for s,pair in stage_thresholds.items(): thresholds[int(s)] = (float(pair[0]), float(pair[1]))
    stage = _num(g, "stage").fillna(0).astype(int)
    for stage_no, scorer in [(1,_stage1_scores),(2,_stage2_scores),(3,_stage3_scores)]:
        stage_idx = g.index[stage.eq(stage_no)]
        if len(stage_idx) == 0: continue
        scores = scorer(g.loc[stage_idx]); confirmed, watch = thresholds[stage_no]; total = np.asarray(scores["total"], dtype=float)
        labels = np.select([total >= confirmed, total >= watch], ["CONFIRMED", "WATCH"], default="REJECT")
        values = {"quality_version":QUALITY_VERSION,"quality_stage":stage_no,"stage_quality_score":np.round(total,2),"stage_quality_label":labels,"stage_rs_score":np.round(scores["rs"],2),"stage_trend_score":np.round(scores["trend"],2),"stage_structure_score":np.round(scores["structure"],2),"stage_volume_score":np.round(scores["volume"],2),"stage_reversal_score":np.round(scores["reversal"],2),"stage_momentum_score":np.round(scores["momentum"],2),"stage_breakout_score":np.round(scores["breakout"],2),"stage_extension_score":np.round(scores["extension"],2),"quality_score":np.round(total,2),"long_quality_score":np.round(total,2),"quality_enhancement_score":np.round(total,2),"long_quality_label":labels,"quality_rs_score":np.round(scores["rs"],2),"quality_trend_score":np.round(scores["trend"],2),"quality_price_structure_score":np.round(scores["structure"],2),"quality_volume_score":np.round(scores["volume"],2),"quality_market_score":0.0,"quality_risk_score":0.0}
        for col,val in values.items(): out.loc[stage_idx,col] = val
    out.loc[g.index, "market_context"] = _market_context(_num(g, "market_score"))
    risk_level, risk_flags = _risk_profile(g); out.loc[g.index,"risk_level"], out.loc[g.index,"risk_flags"] = risk_level, risk_flags
    stage3_idx = g.index[stage.eq(3)]
    if len(stage3_idx):
        retest = _bool(g.loc[stage3_idx], "cloud_retest")
        out.loc[stage3_idx,"stage3_trigger_type"] = np.where(retest.to_numpy(),"CLOUD_RETEST","TENKAN_STRONG_CONFIRMATION")
        deployable = out.loc[stage3_idx,"stage_quality_label"].eq("CONFIRMED")
        out.loc[stage3_idx,"stage3_deployable"] = deployable.to_numpy()
        out.loc[stage3_idx,"stage3_deploy_reason"] = np.where(deployable.to_numpy(),"QUALITY_CONFIRMED_RESEARCH_ONLY","QUALITY_BELOW_CONFIRMED")
    lecture_values = pd.to_numeric(out.loc[g.index,"lecture_score"], errors="coerce").fillna(0.0)
    quality_values = pd.to_numeric(out.loc[g.index,"stage_quality_score"], errors="coerce").fillna(0.0)
    out.loc[g.index,"combined_score"] = np.round(lecture_values.to_numpy()*0.60 + quality_values.to_numpy()*0.40, 2)
    _assign_setup_ids(out, mask)
    ranked = out.loc[mask].sort_values(["signal_date","stage","stage_quality_score","lecture_score","source_rank"], ascending=[True,True,False,False,True], kind="stable")
    ranks = ranked.groupby(["signal_date","stage"]).cumcount() + 1
    out.loc[ranked.index,"daily_stage_quality_rank"] = ranks.astype("Int64").to_numpy(); out.loc[ranked.index,"daily_long_rank"] = ranks.astype("Int64").to_numpy()
    return out
