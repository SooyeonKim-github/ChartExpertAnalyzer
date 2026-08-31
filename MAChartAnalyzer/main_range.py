from __future__ import annotations

import argparse
from pathlib import Path
import re

import numpy as np
import pandas as pd

from analyzer import MAChartSignalAnalyzer
from config import DEFAULT_CONFIG, DEFAULT_INFO_EXCEL, RESULT_DIR
from data_provider import PykrxDataProvider
from position_backtester import ScaleInPlan, empty_position_fields, empty_trade_fields, simulate_scaled_positions
from universe import TickerUniverse


MILESTONES = (1, 5, 10, 20, 40, 60)
CONFIRMED_STATUSES = {"STRONG_CONFIRMED", "CONFIRMED"}


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    parts = re.split(r"[~～]", str(text).replace(" ", ""))
    if len(parts) != 2:
        raise ValueError("YYYYMMDD~YYYYMMDD 형식으로 입력하세요.")
    start = pd.to_datetime(parts[0], format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(parts[1], format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def _ticker(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text else ""


def load_membership(path: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Liquidity membership CSV가 없습니다: {p}")
    m = pd.read_csv(p, encoding="utf-8-sig", dtype={"ticker": str})
    required = {"date", "ticker"}
    missing = required - set(m.columns)
    if missing:
        raise ValueError(f"Membership 필수 컬럼 누락: {sorted(missing)}")
    m = m.copy()
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    m["ticker"] = m["ticker"].map(_ticker)
    m = m[(m["date"] >= start) & (m["date"] <= end)].dropna(subset=["date"])
    return m.drop_duplicates(["date", "ticker"], keep="last").copy()


def forward_metrics(full: pd.DataFrame, pos: int, max_bars: int) -> dict:
    """Forward returns using D+1 open as a realistic standalone entry reference."""
    row: dict = {}
    signal_close = float(full["Close"].iloc[pos])
    entry_pos = pos + 1
    if entry_pos >= len(full):
        row["Entry_Date"] = ""
        row["Entry_Price_D1_Open"] = np.nan
        for n in MILESTONES:
            if n <= max_bars:
                row[f"D+{n}_Close_Return_Pct"] = np.nan
                row[f"Signal_D+{n}_Close_Return_Pct"] = np.nan
        row[f"Forward_Complete_{max_bars}D"] = 0
        row[f"MFE_{max_bars}D_Pct"] = np.nan
        row[f"MAE_{max_bars}D_Pct"] = np.nan
        return row

    entry_price = float(full["Open"].iloc[entry_pos])
    row["Entry_Date"] = full.index[entry_pos].strftime("%Y-%m-%d")
    row["Entry_Price_D1_Open"] = entry_price
    for n in MILESTONES:
        if n > max_bars:
            continue
        j = pos + n
        if j < len(full):
            close_n = float(full["Close"].iloc[j])
            row[f"D+{n}_Close_Return_Pct"] = (close_n / entry_price - 1.0) * 100.0
            row[f"Signal_D+{n}_Close_Return_Pct"] = (close_n / signal_close - 1.0) * 100.0
        else:
            row[f"D+{n}_Close_Return_Pct"] = np.nan
            row[f"Signal_D+{n}_Close_Return_Pct"] = np.nan

    end = min(len(full) - 1, pos + max_bars)
    future = full.iloc[entry_pos : end + 1]
    row[f"Forward_Complete_{max_bars}D"] = int(pos + max_bars < len(full))
    if future.empty:
        row[f"MFE_{max_bars}D_Pct"] = np.nan
        row[f"MAE_{max_bars}D_Pct"] = np.nan
    else:
        row[f"MFE_{max_bars}D_Pct"] = (float(future["High"].max()) / entry_price - 1.0) * 100.0
        row[f"MAE_{max_bars}D_Pct"] = (float(future["Low"].min()) / entry_price - 1.0) * 100.0
    return row


def _trade_summary(trade_events: pd.DataFrame) -> pd.DataFrame:
    if trade_events.empty:
        return pd.DataFrame()
    return (
        trade_events.groupby(["Stage1_Status", "Stage1_Primary_Signal", "Filled_Stages"], dropna=False)
        .agg(
            Trades=("Ticker", "count"),
            Avg_Invested_Return_Pct=("Trade_Return_Pct", "mean"),
            Median_Invested_Return_Pct=("Trade_Return_Pct", "median"),
            Avg_Portfolio_Return_Pct=("Portfolio_Return_Pct", "mean"),
            Median_Portfolio_Return_Pct=("Portfolio_Return_Pct", "median"),
            Win_Rate=("Trade_Return_Pct", lambda s: float((pd.to_numeric(s, errors="coerce") > 0).mean())),
            Avg_Holding_Bars=("Trade_Holding_Bars", "mean"),
            Avg_MFE_Pct=("Trade_MFE_Pct", "mean"),
            Avg_MAE_Pct=("Trade_MAE_Pct", "mean"),
        )
        .reset_index()
    )


def run_range(args) -> int:
    cfg = DEFAULT_CONFIG
    start, end = parse_date_range(args.date_range)
    membership = load_membership(args.membership_csv, start, end)
    universe = TickerUniverse(args.info_excel).get(args.top_n, args.sort_by)
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    analyzer = MAChartSignalAnalyzer(cfg)
    plan = ScaleInPlan(
        stage1_weight=cfg.stage1_allocation_pct / 100.0,
        stage2_weight=cfg.stage2_allocation_pct / 100.0,
        stage3_weight=cfg.stage3_allocation_pct / 100.0,
    )

    fetch_start = start - pd.Timedelta(days=cfg.history_calendar_days)
    requested_future_end = end + pd.Timedelta(days=max(120, args.forward_bars * 4))
    fetch_end = min(requested_future_end, pd.Timestamp.today().normalize())
    mode = "point-in-time liquidity membership" if not membership.empty else "static input universe"
    print(
        f"[INFO] MA V3 range={start.date()}~{end.date()} universe_union={len(universe)} "
        f"mode={mode} fetch={fetch_start.date()}~{fetch_end.date()} forward={args.forward_bars}"
    )
    print(
        f"[INFO] scale-in={cfg.stage1_allocation_pct:.0f}%/"
        f"{cfg.stage2_allocation_pct:.0f}%/{cfg.stage3_allocation_pct:.0f}% | cooldown=REMOVED"
    )

    membership_by_ticker: dict[str, pd.DataFrame] = {}
    if not membership.empty:
        membership_by_ticker = {
            ticker: frame.set_index("date").sort_index()
            for ticker, frame in membership.groupby("ticker")
        }

    rows: list[dict] = []
    trade_rows: list[dict] = []
    entry_rows: list[dict] = []

    for ti, info in enumerate(universe, 1):
        try:
            full = provider.get_ohlcv(
                info.ticker,
                fetch_start.strftime("%Y-%m-%d"),
                fetch_end.strftime("%Y-%m-%d"),
            )
            if len(full) < cfg.min_history_bars:
                continue

            allowed = membership_by_ticker.get(info.ticker)
            if not membership.empty and allowed is None:
                continue
            allowed_dates = set(allowed.index) if allowed is not None else None

            positions = [
                i for i, dt in enumerate(full.index)
                if start <= pd.Timestamp(dt).normalize() <= end
                and (allowed_dates is None or pd.Timestamp(dt).normalize() in allowed_dates)
            ]

            ticker_rows: list[dict] = []
            signal_events: list[dict] = []
            for pos in positions:
                if pos < cfg.min_history_bars - 1:
                    continue
                hist = full.iloc[: pos + 1]
                signal_date = hist.index[-1].strftime("%Y-%m-%d")
                result = analyzer.analyze(info.ticker, info.name, info.market, signal_date, hist)
                row = result.to_row()

                if allowed is not None:
                    key = pd.Timestamp(hist.index[-1]).normalize()
                    if key in allowed.index:
                        m = allowed.loc[key]
                        if isinstance(m, pd.DataFrame):
                            m = m.iloc[-1]
                        row["Universe_Rank"] = m.get("source_rank", np.nan)
                        row["Avg_Trading_Value_20D"] = m.get("avg_trading_value_20d", np.nan)
                        row["Universe_Mode"] = "LIQUIDITY_20D_POINT_IN_TIME"
                else:
                    row["Universe_Rank"] = np.nan
                    row["Avg_Trading_Value_20D"] = np.nan
                    row["Universe_Mode"] = "STATIC_INPUT_UNIVERSE"

                row.update(forward_metrics(full, pos, args.forward_bars))
                row.update(empty_position_fields())
                row.update(empty_trade_fields())
                row_idx = len(ticker_rows)
                ticker_rows.append(row)

                if result.status in CONFIRMED_STATUSES:
                    signal_events.append(
                        {
                            "row_idx": row_idx,
                            "pos": pos,
                            "signal_date": signal_date,
                            "status": result.status,
                            "signal": result.primary_signal,
                            "signal_low": float(hist["Low"].iloc[-1]),
                        }
                    )

            annotations, ticker_trades, ticker_entries = simulate_scaled_positions(
                full=full,
                signal_events=signal_events,
                ticker=info.ticker,
                name=info.name,
                market=info.market,
                short_ma_period=cfg.short_ma_period,
                max_bars=args.forward_bars,
                plan=plan,
            )
            for row_idx, ann in annotations.items():
                if 0 <= row_idx < len(ticker_rows):
                    ticker_rows[row_idx].update(ann)

            rows.extend(ticker_rows)
            trade_rows.extend(ticker_trades)
            entry_rows.extend(ticker_entries)

            if ti % 10 == 0:
                print(
                    f"[INFO] progress {ti}/{len(universe)} rows={len(rows)} "
                    f"positions={len(trade_rows)} entries={len(entry_rows)}"
                )
        except Exception as exc:
            print(f"[WARN] {info.ticker} {info.name}: {exc}")

    if not rows:
        print("[ERROR] 기간 분석 결과 없음")
        return 1

    all_results = pd.DataFrame(rows)
    trade_events = pd.DataFrame(trade_rows)
    position_entries = pd.DataFrame(entry_rows)
    range_key = f"{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    out_dir = RESULT_DIR / f"range_{range_key}"
    out_dir.mkdir(parents=True, exist_ok=True)

    confirmed_mask = all_results["Status"].isin(CONFIRMED_STATUSES)
    watch_mask = all_results["Status"].eq("WATCH")
    candidates = all_results[confirmed_mask | watch_mask].copy()

    all_results.to_csv(out_dir / "range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")
    trade_events.to_csv(out_dir / "trade_events.csv", index=False, encoding="utf-8-sig")
    position_entries.to_csv(out_dir / "position_entries.csv", index=False, encoding="utf-8-sig")

    summary = (
        all_results.groupby("Status", dropna=False)
        .agg(Count=("Ticker", "count"), Avg_Score=("Score", "mean"), Avg_Timing=("Timing_Score", "mean"))
        .reset_index()
    )
    forward_cols = [c for c in all_results.columns if c.startswith("D+") and c.endswith("_Close_Return_Pct")]
    if forward_cols:
        avg = all_results.groupby("Status")[forward_cols].mean().reset_index()
        summary = summary.merge(avg, on="Status", how="left")

    trade_summary = _trade_summary(trade_events)
    stage_summary = pd.DataFrame()
    if not position_entries.empty:
        stage_summary = (
            position_entries.groupby(["Stage", "Primary_Signal"], dropna=False)
            .agg(
                Entries=("Ticker", "count"),
                Avg_Entry_Price=("Entry_Price", "mean"),
                Avg_Stop_After_Entry=("Position_Stop_After_Entry", "mean"),
            )
            .reset_index()
        )

    with pd.ExcelWriter(out_dir / "ma_range_backtest.xlsx", engine="openpyxl") as writer:
        all_results.to_excel(writer, sheet_name="AllResults", index=False)
        candidates.to_excel(writer, sheet_name="Candidates", index=False)
        trade_events.to_excel(writer, sheet_name="TradeEvents", index=False)
        position_entries.to_excel(writer, sheet_name="PositionEntries", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
        trade_summary.to_excel(writer, sheet_name="TradeSummary", index=False)
        stage_summary.to_excel(writer, sheet_name="StageSummary", index=False)
        cfg_rows = [{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]
        cfg_rows += [
            {"Parameter": "date_range", "Value": args.date_range},
            {"Parameter": "top_n", "Value": args.top_n},
            {"Parameter": "sort_by", "Value": args.sort_by},
            {"Parameter": "forward_bars", "Value": args.forward_bars},
            {"Parameter": "membership_csv", "Value": args.membership_csv},
            {"Parameter": "cooldown", "Value": "REMOVED"},
            {"Parameter": "entry_rule", "Value": "stateful 3-stage scale-in; every fill at next open"},
            {"Parameter": "stage1_rule", "Value": "first confirmed signal while flat"},
            {"Parameter": "stage2_rule", "Value": "BOX_RETEST_CONFIRMED while stage1 position is open"},
            {"Parameter": "stage3_rule", "Value": "later BOX/PRIOR_HIGH/strong-pullback confirmation after stage2"},
            {"Parameter": "exit_rule", "Value": "raised signal-low stop -> short MA close -> time exit"},
        ]
        pd.DataFrame(cfg_rows).to_excel(writer, sheet_name="Config", index=False)

    counts = all_results["Status"].value_counts()
    stage_counts = position_entries["Stage"].value_counts() if not position_entries.empty else pd.Series(dtype="int64")
    print(f"[DONE] {out_dir}")
    print(
        f"[INFO] STRONG={int(counts.get('STRONG_CONFIRMED', 0))} "
        f"CONFIRMED={int(counts.get('CONFIRMED', 0))} "
        f"WATCH={int(counts.get('WATCH', 0))} REJECTED={int(counts.get('REJECTED', 0))}"
    )
    print(
        f"[INFO] POSITIONS={len(trade_events)} "
        f"STAGE1={int(stage_counts.get(1, 0))} "
        f"STAGE2={int(stage_counts.get(2, 0))} "
        f"STAGE3={int(stage_counts.get(3, 0))}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="MAChartAnalyzer V3 stateful scale-in range backtest")
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--info-excel", default=str(DEFAULT_INFO_EXCEL))
    p.add_argument("--membership-csv", default="", help="point-in-time liquidity membership CSV")
    p.add_argument("--top-n", type=int, default=100)
    p.add_argument("--sort-by", default="market_cap", choices=["market_cap", "trading_value", "volume"])
    p.add_argument("--forward-bars", type=int, default=60)
    p.add_argument("--no-cache", action="store_true")
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
