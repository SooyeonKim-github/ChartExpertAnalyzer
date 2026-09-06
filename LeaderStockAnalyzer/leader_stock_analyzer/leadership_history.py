from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LeadershipHistoryContext:
    """Shared point-in-time history used by persistence and emerging features.

    Frames are built from the candidate pool available to the provider.  During
    range scans this is the preloaded Excel candidate pool (TOP N multiplied by
    candidate_multiplier), so rank history is broader than the final daily
    Leader TOP N universe.
    """

    value_df: pd.DataFrame
    rank_df: pd.DataFrame
    rank_percentile_df: pd.DataFrame
    return_df: pd.DataFrame
    close_df: pd.DataFrame

    @classmethod
    def build(
        cls,
        daily_by_ticker: dict[str, pd.DataFrame],
        *,
        scan_date: str | pd.Timestamp | None = None,
    ) -> "LeadershipHistoryContext":
        value_series: dict[str, pd.Series] = {}
        close_series: dict[str, pd.Series] = {}
        return_series: dict[str, pd.Series] = {}
        target = pd.Timestamp(scan_date).normalize() if scan_date is not None else None

        for raw_ticker, frame in daily_by_ticker.items():
            ticker = str(raw_ticker).zfill(6)
            if frame is None or frame.empty:
                continue
            df = frame.copy()
            df.index = pd.to_datetime(df.index, errors="coerce")
            df = df[~df.index.isna()].sort_index()
            if target is not None:
                df = df[df.index.normalize() <= target]
            if df.empty:
                continue

            if "trading_value" in df.columns:
                value = pd.to_numeric(df["trading_value"], errors="coerce")
                if "close" in df.columns and "volume" in df.columns:
                    close_for_value = pd.to_numeric(df["close"], errors="coerce")
                    volume = pd.to_numeric(df["volume"], errors="coerce")
                    value = value.where(value > 0, close_for_value * volume)
                value_series[ticker] = value.rename(ticker)

            if "close" in df.columns:
                close = pd.to_numeric(df["close"], errors="coerce").rename(ticker)
                close_series[ticker] = close
                return_series[ticker] = close.pct_change(fill_method=None).mul(100.0).rename(ticker)

        value_df = pd.DataFrame(value_series).sort_index() if value_series else pd.DataFrame()
        close_df = pd.DataFrame(close_series).sort_index() if close_series else pd.DataFrame()
        return_df = pd.DataFrame(return_series).sort_index() if return_series else pd.DataFrame()

        if value_df.empty:
            rank_df = pd.DataFrame(index=value_df.index)
            percentile_df = pd.DataFrame(index=value_df.index)
        else:
            rank_df = value_df.rank(axis=1, method="min", ascending=False, na_option="keep")
            counts = value_df.notna().sum(axis=1).astype(float)
            percentile_df = rank_df.copy()
            for dt in rank_df.index:
                count = float(counts.get(dt, 0.0))
                if count <= 1:
                    percentile_df.loc[dt] = rank_df.loc[dt].where(rank_df.loc[dt].isna(), 100.0)
                else:
                    percentile_df.loc[dt] = (
                        (count - rank_df.loc[dt]) / (count - 1.0) * 100.0
                    )

        return cls(
            value_df=value_df,
            rank_df=rank_df,
            rank_percentile_df=percentile_df,
            return_df=return_df,
            close_df=close_df,
        )

    @property
    def available(self) -> bool:
        return not self.rank_df.empty

    def ranks(self, ticker: str) -> pd.Series:
        code = str(ticker).zfill(6)
        if code not in self.rank_df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(self.rank_df[code], errors="coerce").dropna()

    def rank_percentiles(self, ticker: str) -> pd.Series:
        code = str(ticker).zfill(6)
        if code not in self.rank_percentile_df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(self.rank_percentile_df[code], errors="coerce").dropna()

    def trading_values(self, ticker: str) -> pd.Series:
        code = str(ticker).zfill(6)
        if code not in self.value_df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(self.value_df[code], errors="coerce").dropna()

    def closes(self, ticker: str) -> pd.Series:
        code = str(ticker).zfill(6)
        if code not in self.close_df.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(self.close_df[code], errors="coerce").dropna()
