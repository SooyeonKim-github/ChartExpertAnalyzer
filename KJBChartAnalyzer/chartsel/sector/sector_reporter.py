from __future__ import annotations

from pathlib import Path
import pandas as pd


class SectorReporter:
    """V3 섹터 강도/수급 결과 저장 도우미.

    사용자 기존 SectorReporter의 저장 방식을 유지하면서 가격 RS/Composite 컬럼을 함께 출력한다.
    """

    def __init__(self, results_dir: str | Path, charts_dir: str | Path | None = None, sector_col: str = "네이버_업종명"):
        self.results_dir = Path(results_dir)
        self.charts_dir = Path(charts_dir) if charts_dir else self.results_dir / "charts"
        self.sector_col = sector_col
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.charts_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_filename(value: str) -> str:
        keep = [ch if ch.isalnum() or ch in ["_", "-", " "] else "_" for ch in str(value)]
        return "".join(keep).strip().replace(" ", "_")[:80]

    def save_daily(self, sector_daily: pd.DataFrame, prefix: str = "sector_strength") -> tuple[Path, Path]:
        csv_path = self.results_dir / f"{prefix}_daily.csv"
        xlsx_path = self.results_dir / f"{prefix}_daily.xlsx"
        sector_daily.to_csv(csv_path, index=False, encoding="utf-8-sig")
        sector_daily.to_excel(xlsx_path, index=False)
        return csv_path, xlsx_path

    def latest_ranking(self, sector_daily: pd.DataFrame, target_date=None, top_n: int = 15) -> pd.DataFrame:
        if sector_daily is None or sector_daily.empty:
            return pd.DataFrame()
        df = sector_daily.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        target = df["Date"].max() if target_date is None else pd.to_datetime(target_date)
        available = df[df["Date"] <= target]
        if available.empty:
            return pd.DataFrame()
        target = available["Date"].max()
        x = df[df["Date"] == target].copy()
        sort_cols = [c for c in ["Sector_Composite_Score", "Sector_RS_Score", "Sector_Flow_Score", "Relative_TV_Strength_20"] if c in x.columns]
        if sort_cols:
            x = x.sort_values(sort_cols, ascending=False)
        return x.head(top_n).reset_index(drop=True)

    def save_top_sector_charts(self, sector_daily: pd.DataFrame, ranking_df: pd.DataFrame, lookback_days: int = 120) -> list[Path]:
        if sector_daily is None or sector_daily.empty or ranking_df is None or ranking_df.empty:
            return []
        import matplotlib.pyplot as plt
        df = sector_daily.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        saved = []
        for sector_name in ranking_df[self.sector_col].dropna().astype(str).tolist():
            x = df[df[self.sector_col].astype(str) == sector_name].sort_values("Date").tail(lookback_days)
            if x.empty:
                continue
            path = self.charts_dir / f"{self._safe_filename(sector_name)}_sector_strength.png"
            plt.figure(figsize=(12, 5))
            if "Sector_Composite_Score" in x.columns:
                plt.plot(x["Date"], x["Sector_Composite_Score"], label="Sector Composite")
            if "Sector_RS_Score" in x.columns:
                plt.plot(x["Date"], x["Sector_RS_Score"], label="Sector RS")
            if "Sector_Flow_Score_100" in x.columns:
                plt.plot(x["Date"], x["Sector_Flow_Score_100"], label="Sector Flow")
            plt.title(f"{sector_name} Sector Strength")
            plt.xlabel("Date")
            plt.ylabel("Score")
            plt.ylim(0, 100)
            plt.legend()
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(path, dpi=150)
            plt.close()
            saved.append(path)
        return saved
