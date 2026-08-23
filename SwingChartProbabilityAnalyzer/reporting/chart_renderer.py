from __future__ import annotations

from pathlib import Path
import re

import matplotlib.pyplot as plt
import pandas as pd

from config import StrategyConfig
from core.bottom_analyzer import add_moving_averages
from core.models import AnalysisResult


def _safe(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", s)


def render_chart(df: pd.DataFrame, result: AnalysisResult, cfg: StrategyConfig, out_dir: Path, bars: int = 120) -> Path | None:
    if result.channel is None or df.empty:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    x = add_moving_averages(df, cfg.ma_periods)
    start = max(0, len(x)-bars)
    view = x.iloc[start:].copy()
    global_pos = list(range(start, len(x)))
    dates = view.index
    stem = f"{result.ticker}_{_safe(result.name)}"

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(dates, view["Close"], linewidth=1.6, label="Close")
    for p in cfg.ma_periods:
        ax.plot(dates, view[f"MA{p}"], linewidth=1.0, label=f"MA{p}")
    ch = result.channel
    upper = [ch.upper(i) for i in global_pos]
    lower = [ch.lower(i) for i in global_pos]
    mid = [(u+l)/2 for u,l in zip(upper, lower)]
    ax.plot(dates, upper, linestyle="--", linewidth=1.2, label="Channel upper")
    ax.plot(dates, mid, linestyle=":", linewidth=1.1, label="Channel mid")
    ax.plot(dates, lower, linestyle="--", linewidth=1.2, label="Channel lower")
    ref_date = result.metrics.get("Reference_Date")
    if ref_date:
        ts = pd.Timestamp(ref_date)
        if ts in view.index:
            ax.axvline(ts, linestyle=":", linewidth=1.0, label="Volume reference")
    ax.set_title(f"{result.name} ({result.ticker}) | {result.status} | Score {result.score}")
    ax.grid(alpha=0.2); ax.legend(loc="best", ncol=2)
    fig.autofmt_xdate(); fig.tight_layout()
    price_path = out_dir / f"{stem}_price.png"
    fig.savefig(price_path, dpi=140); plt.close(fig)

    # 영상에서 중요한 '바닥권 거래량 급증'을 별도 그림으로 확인할 수 있게 저장.
    vol = view["Volume"]
    vol_avg = vol.shift(1).rolling(cfg.volume_avg_period).mean()
    fig2, ax2 = plt.subplots(figsize=(14, 3.8))
    ax2.bar(dates, vol, width=1.0, label="Volume")
    ax2.plot(dates, vol_avg, linewidth=1.2, label=f"Previous {cfg.volume_avg_period}D avg")
    if ref_date:
        ts = pd.Timestamp(ref_date)
        if ts in view.index:
            ax2.axvline(ts, linestyle=":", linewidth=1.0, label="Reference candle")
    ax2.set_title(f"{result.name} ({result.ticker}) | Bottom-volume check")
    ax2.grid(alpha=0.2); ax2.legend(loc="best")
    fig2.autofmt_xdate(); fig2.tight_layout()
    fig2.savefig(out_dir / f"{stem}_volume.png", dpi=140); plt.close(fig2)
    return price_path
