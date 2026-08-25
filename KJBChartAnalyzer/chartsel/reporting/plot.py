from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt


def plot_analysis(df, result, out_path: str, status: str | None = None):
    x = df.tail(180)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(x.index, x['Close'], label='Close')
    for col in ['MA5', 'MA20', 'MA60', 'MA120']:
        if col in x:
            ax.plot(x.index, x[col], label=col, linewidth=1)
    if 'BB_UPPER' in x:
        ax.plot(x.index, x['BB_UPPER'], label='BB Upper', linewidth=.8)
        ax.plot(x.index, x['BB_LOWER'], label='BB Lower', linewidth=.8)
    for lv in result.support_levels[-3:]:
        ax.axhline(lv, linestyle='--', linewidth=.7)
    for lv in result.resistance_levels[-3:]:
        ax.axhline(lv, linestyle=':', linewidth=.7)

    status_text = f' | {status}' if status else ''
    ax.set_title(
        f'{result.ticker}{status_text} | Selection {result.total_score:.1f} | '
        f'Technical {result.technical_score:.1f} | Timing {result.timing_score:.1f} | '
        f'Leader {result.leader_score:.1f} | RS {result.relative_strength_score:.1f} | '
        f'Risk {result.risk_score:.1f} | {result.entry_status}'
    )
    ax.legend(ncol=4)
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(p, dpi=140)
    plt.close(fig)
