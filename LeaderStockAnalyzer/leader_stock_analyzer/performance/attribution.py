from __future__ import annotations

from pathlib import Path

import pandas as pd


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _bucket_sector_rank(series: pd.Series) -> pd.Series:
    s = _numeric(series)
    return pd.cut(s, bins=[0, 3, 5, 10, 20, float("inf")], labels=["1-3", "4-5", "6-10", "11-20", "21+"], include_lowest=True)


def _bucket_persistence(series: pd.Series) -> pd.Series:
    s = _numeric(series)
    return pd.cut(s, bins=[-0.001, 39.999, 59.999, 79.999, 100.001], labels=["0-39", "40-59", "60-79", "80-100"], include_lowest=True)


def _bucket_leader(series: pd.Series) -> pd.Series:
    s = _numeric(series)
    return pd.cut(s, bins=[-float("inf"), 64.999, 74.999, 84.999, 89.999, float("inf")], labels=["<65", "65-74", "75-84", "85-89", "90+"])


def _bucket_timing(series: pd.Series) -> pd.Series:
    s = _numeric(series)
    return pd.cut(s, bins=[-float("inf"), 49.999, 64.999, 74.999, 84.999, float("inf")], labels=["<50", "50-64", "65-74", "75-84", "85+"])


def _bucket_chase(series: pd.Series) -> pd.Series:
    s = _numeric(series)
    return pd.cut(s, bins=[-float("inf"), 39.999, 59.999, 79.999, float("inf")], labels=["LOW", "MEDIUM", "HIGH", "EXTREME"])


class PerformanceAttributionEngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pcfg = cfg.get("performance", {})
        self.min_group_count = int(self.pcfg.get("min_group_count", 20))

    def _summary(self, frame: pd.DataFrame) -> dict:
        out: dict[str, float | int | str | None] = {"count": int(len(frame))}
        for h in (5, 20, 60):
            col = f"D+{h}"
            if col in frame.columns:
                s = _numeric(frame[col]).dropna()
                out[f"complete_count_D{h}"] = int(len(s))
                out[f"avg_D{h}"] = round(float(s.mean()), 3) if not s.empty else None
                out[f"median_D{h}"] = round(float(s.median()), 3) if not s.empty else None
                out[f"win_rate_D{h}"] = round(float((s > 0).mean() * 100.0), 2) if not s.empty else None
        for col in ("MFE_D20", "MAE_D20"):
            if col in frame.columns:
                s = _numeric(frame[col]).dropna()
                out[f"avg_{col}"] = round(float(s.mean()), 3) if not s.empty else None
                out[f"median_{col}"] = round(float(s.median()), 3) if not s.empty else None
        if "D+20" in frame.columns:
            s = _numeric(frame["D+20"]).dropna()
            out["p25_D20"] = round(float(s.quantile(0.25)), 3) if not s.empty else None
            out["p75_D20"] = round(float(s.quantile(0.75)), 3) if not s.empty else None
        if "excursion_ratio_D20" in frame.columns:
            s = _numeric(frame["excursion_ratio_D20"]).replace([float("inf"), -float("inf")], pd.NA).dropna()
            out["avg_excursion_ratio_D20"] = round(float(s.mean()), 4) if not s.empty else None
        if "mfe_capture_D20" in frame.columns:
            s = _numeric(frame["mfe_capture_D20"]).replace([float("inf"), -float("inf")], pd.NA).dropna()
            out["avg_mfe_capture_D20"] = round(float(s.mean()), 4) if not s.empty else None
        if "failed_within_D3" in frame.columns:
            s = frame["failed_within_D3"].dropna()
            if not s.empty:
                values = s.map(lambda x: str(x).lower() in {"true", "1"} if not isinstance(x, bool) else x)
                out["failed_within_D3_rate"] = round(float(values.mean() * 100.0), 2)
            else:
                out["failed_within_D3_rate"] = None
        effective = int(out.get("complete_count_D20", 0) or 0)
        out["sample_quality"] = "OK" if effective >= self.min_group_count else "LOW_SAMPLE"
        return out

    def _group(self, df: pd.DataFrame, key: str) -> pd.DataFrame:
        if key not in df.columns:
            return pd.DataFrame()
        rows: list[dict] = []
        valid = df[df[key].notna()].copy()
        for value, grp in valid.groupby(key, observed=True, dropna=False):
            row = {key: str(value)}
            row.update(self._summary(grp))
            rows.append(row)
        return pd.DataFrame(rows)

    def _combinations(self, df: pd.DataFrame) -> pd.DataFrame:
        masks: dict[str, pd.Series] = {}
        index = df.index
        true = pd.Series(True, index=index)

        quality = df.get("breakout_quality_label", pd.Series(index=index, dtype=object)).astype(str)
        sector_rank = _numeric(df.get("sector_market_rank", pd.Series(index=index, dtype=float)))
        persistence = df.get("leader_persistence_level", pd.Series(index=index, dtype=object)).astype(str)
        leader_type = df.get("leader_type", pd.Series(index=index, dtype=object)).astype(str)
        leader = _numeric(df.get("leader_score", pd.Series(index=index, dtype=float)))
        timing = _numeric(df.get("timing_score", pd.Series(index=index, dtype=float)))
        chase = _numeric(df.get("chase_risk", pd.Series(index=index, dtype=float)))

        masks["CLEAN_BREAKOUT"] = quality.eq("CLEAN_BREAKOUT")
        masks["CLEAN+SECTOR_TOP5"] = quality.eq("CLEAN_BREAKOUT") & sector_rank.between(1, 5)
        masks["CLEAN+PERSISTENCE_HIGH"] = quality.eq("CLEAN_BREAKOUT") & persistence.eq("HIGH")
        masks["CLEAN+EMERGING"] = quality.eq("CLEAN_BREAKOUT") & leader_type.eq("EMERGING_LEADER")
        masks["LEADER85+TIMING75"] = (leader >= 85) & (timing >= 75)
        masks["LEADER85+TIMING75+CHASE_LT60"] = (leader >= 85) & (timing >= 75) & (chase < 60)
        masks["LEADER85+SECTOR_TOP5"] = (leader >= 85) & sector_rank.between(1, 5)
        masks["PERSISTENT+CHASE_LT60"] = persistence.eq("HIGH") & (chase < 60)
        masks["ALL"] = true

        rows: list[dict] = []
        for name, mask in masks.items():
            grp = df[mask.fillna(False)].copy()
            row = {"condition": name}
            row.update(self._summary(grp))
            rows.append(row)
        return pd.DataFrame(rows)

    def build_reports(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        if df is None or df.empty:
            return {"overall_summary": pd.DataFrame([self._summary(pd.DataFrame())])}

        work = df.copy()
        if "sector_market_rank" in work.columns:
            work["sector_rank_bucket"] = _bucket_sector_rank(work["sector_market_rank"])
        if "leader_persistence_score" in work.columns:
            work["persistence_score_bucket"] = _bucket_persistence(work["leader_persistence_score"])
        if "leader_score" in work.columns:
            work["leader_score_bucket"] = _bucket_leader(work["leader_score"])
        if "timing_score" in work.columns:
            work["timing_score_bucket"] = _bucket_timing(work["timing_score"])
        if "chase_risk" in work.columns:
            work["chase_risk_bucket"] = _bucket_chase(work["chase_risk"])

        reports = {
            "overall_summary": pd.DataFrame([self._summary(work)]),
            "performance_by_status": self._group(work, "status"),
            "performance_by_breakout_quality": self._group(work, "breakout_quality_label"),
            "performance_by_leader_type": self._group(work, "leader_type"),
            "performance_by_sector_rank": self._group(work, "sector_rank_bucket"),
            "performance_by_persistence": self._group(work, "leader_persistence_level"),
            "performance_by_persistence_score": self._group(work, "persistence_score_bucket"),
            "performance_by_leader_score": self._group(work, "leader_score_bucket"),
            "performance_by_timing_score": self._group(work, "timing_score_bucket"),
            "performance_by_chase_risk": self._group(work, "chase_risk_bucket"),
            "performance_by_combinations": self._combinations(work),
        }
        return reports

    def write_reports(self, df: pd.DataFrame, out_dir: str | Path) -> dict[str, Path]:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        for name, report in self.build_reports(df).items():
            path = root / f"{name}.csv"
            report.to_csv(path, index=False, encoding="utf-8-sig")
            paths[name] = path
        return paths
