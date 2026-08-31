from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dynamic_chart_analyzer import DynamicChartAnalyzer, StrategyConfig
from dynamic_chart_analyzer.providers import load_pykrx

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RangeParams:
    start: pd.Timestamp
    end: pd.Timestamp
    top_n: int
    sort_by: str
    forward_bars: int
    history_days: int
    capital: float
    use_risk_cap: bool
    use_stop: bool
    include_dynamic_rsi: bool


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    raw = str(text or "").strip().replace(" ", "")
    if "~" not in raw:
        raise ValueError("Date range must be YYYYMMDD~YYYYMMDD, e.g. 20260401~20260531")
    left, right = raw.split("~", 1)
    start = pd.to_datetime(left, format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(right, format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError(f"Start date is after end date: {start.date()} > {end.date()}")
    return start, end


def _import_pykrx():
    try:
        from pykrx import stock
    except ImportError as exc:
        raise RuntimeError("pykrx is not installed. Run: pip install -r requirements.txt") from exc
    return stock


def _latest_market_date(stock, requested: pd.Timestamp, max_lookback_days: int = 14) -> str:
    for i in range(max_lookback_days + 1):
        d = requested - pd.Timedelta(days=i)
        ds = d.strftime("%Y%m%d")
        try:
            cap = stock.get_market_cap_by_ticker(ds, market="ALL")
            if cap is not None and not cap.empty:
                return ds
        except Exception:
            pass
    raise RuntimeError(f"Could not resolve a KRX trading date near {requested.date()}")


def _get_universe(snapshot_date: str, top_n: int, sort_by: str) -> pd.DataFrame:
    stock = _import_pykrx()
    cap = stock.get_market_cap_by_ticker(snapshot_date, market="ALL").copy()
    if cap.empty:
        raise RuntimeError(f"No market-cap data returned for {snapshot_date}")

    cap.index = cap.index.astype(str).str.zfill(6)
    cap.index.name = "ticker"
    cap = cap.rename(columns={"시가총액": "market_cap", "상장주식수": "shares"})

    try:
        daily = stock.get_market_ohlcv_by_ticker(snapshot_date, market="ALL").copy()
        daily.index = daily.index.astype(str).str.zfill(6)
        daily = daily.rename(columns={"거래량": "volume", "거래대금": "trading_value", "종가": "close"})
        keep = [c for c in ["volume", "trading_value", "close"] if c in daily.columns]
        if keep:
            cap = cap.join(daily[keep], how="left")
    except Exception:
        pass

    sort_column = {
        "market_cap": "market_cap",
        "trading_value": "trading_value",
        "volume": "volume",
    }[sort_by]
    if sort_column not in cap.columns:
        raise RuntimeError(f"Sort column '{sort_column}' is unavailable from pykrx on {snapshot_date}")

    cap[sort_column] = pd.to_numeric(cap[sort_column], errors="coerce")
    cap = cap.dropna(subset=[sort_column])
    cap = cap[cap[sort_column] > 0].sort_values(sort_column, ascending=False)
    if top_n > 0:
        cap = cap.head(top_n)

    names = []
    for ticker in cap.index:
        try:
            names.append(stock.get_market_ticker_name(ticker))
        except Exception:
            names.append("")
    cap.insert(0, "name", names)
    cap.insert(0, "source_rank", range(1, len(cap) + 1))
    return cap.reset_index()


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out


def _direction(action: str) -> int:
    return -1 if str(action).startswith("SHORT_") else 1


def _add_forward_metrics(
    event: dict,
    price_df: pd.DataFrame,
    forward_bars: int,
) -> dict:
    out = dict(event)
    signal_date = pd.Timestamp(out["signal_date"])
    entry = float(out["entry_price"])
    direction = int(out["direction"])

    positions = np.flatnonzero(price_df.index.normalize() == signal_date.normalize())
    if len(positions) == 0 or not math.isfinite(entry) or entry <= 0:
        for h in range(1, forward_bars + 1):
            out[f"D+{h}"] = np.nan
        out[f"MFE_D+{forward_bars}"] = np.nan
        out[f"MAE_D+{forward_bars}"] = np.nan
        out["forward_available_bars"] = 0
        out["forward_complete"] = False
        return out

    idx = int(positions[0])
    available = max(0, min(forward_bars, len(price_df) - idx - 1))
    for h in range(1, forward_bars + 1):
        if idx + h < len(price_df):
            future = float(price_df["close"].iloc[idx + h])
            raw = future / entry - 1.0
            out[f"D+{h}"] = direction * raw
        else:
            out[f"D+{h}"] = np.nan

    out["forward_available_bars"] = available
    out["forward_complete"] = bool(available >= forward_bars)
    if available:
        fwd = price_df.iloc[idx + 1: idx + available + 1]
        if direction > 0:
            out[f"MFE_D+{forward_bars}"] = float(fwd["high"].max() / entry - 1.0)
            out[f"MAE_D+{forward_bars}"] = float(fwd["low"].min() / entry - 1.0)
        else:
            out[f"MFE_D+{forward_bars}"] = float(1.0 - fwd["low"].min() / entry)
            out[f"MAE_D+{forward_bars}"] = float(1.0 - fwd["high"].max() / entry)
    else:
        out[f"MFE_D+{forward_bars}"] = np.nan
        out[f"MAE_D+{forward_bars}"] = np.nan
    return out


def _build_summary(events: pd.DataFrame, forward_bars: int) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(columns=["side", "stage", "count"])

    horizons = [h for h in [1, 5, 10, 20, 40, 60] if h <= forward_bars]
    rows: list[dict] = []
    for (side, stage), g in events.groupby(["side", "stage"], dropna=False):
        row: dict[str, object] = {
            "side": side,
            "stage": int(stage),
            "count": int(len(g)),
            "complete_count": int(g["forward_complete"].fillna(False).sum()),
        }
        for h in horizons:
            col = f"D+{h}"
            vals = pd.to_numeric(g[col], errors="coerce").dropna()
            row[f"avg_{col}"] = float(vals.mean()) if len(vals) else np.nan
            row[f"median_{col}"] = float(vals.median()) if len(vals) else np.nan
            row[f"win_rate_{col}"] = float((vals > 0).mean()) if len(vals) else np.nan
        mfe_col = f"MFE_D+{forward_bars}"
        mae_col = f"MAE_D+{forward_bars}"
        row[f"avg_{mfe_col}"] = float(pd.to_numeric(g[mfe_col], errors="coerce").mean())
        row[f"avg_{mae_col}"] = float(pd.to_numeric(g[mae_col], errors="coerce").mean())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["side", "stage"]).reset_index(drop=True)


def _write_excel(path: Path, events: pd.DataFrame, summary: pd.DataFrame, universe: pd.DataFrame, errors: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        events.to_excel(writer, sheet_name="Events", index=False)
        universe.to_excel(writer, sheet_name="Universe", index=False)
        errors.to_excel(writer, sheet_name="Errors", index=False)


def run_range(args) -> int:
    start, end = parse_date_range(args.date_range)
    params = RangeParams(
        start=start,
        end=end,
        top_n=args.top_n,
        sort_by=args.sort_by,
        forward_bars=args.forward_bars,
        history_days=args.history_days,
        capital=args.capital,
        use_risk_cap=args.risk_cap,
        use_stop=not args.no_stop,
        include_dynamic_rsi=args.dynamic_rsi,
    )

    stock = _import_pykrx()
    snapshot = _latest_market_date(stock, end)
    universe = _get_universe(snapshot, params.top_n, params.sort_by)

    history_start = (start - pd.Timedelta(days=params.history_days)).strftime("%Y%m%d")
    forward_end = (end + pd.Timedelta(days=max(120, params.forward_bars * 3))).strftime("%Y%m%d")

    cfg = StrategyConfig(
        total_capital=params.capital,
        use_two_percent_risk_cap=params.use_risk_cap,
        use_protective_stop=params.use_stop,
    )
    analyzer = DynamicChartAnalyzer(cfg, include_dynamic_rsi=params.include_dynamic_rsi)

    print("=" * 78)
    print("DynamicChartAnalyzer Range Backtest - fixed 1:2:7")
    print("=" * 78)
    print(f"Date range       : {start:%Y%m%d}~{end:%Y%m%d}")
    print(f"Universe snapshot: {snapshot}")
    print(f"Universe TOP N   : {len(universe)}")
    print(f"Sort by          : {params.sort_by}")
    print(f"Forward bars     : {params.forward_bars}")
    print(f"Capital          : {params.capital:,.0f} KRW (1m / 2m / 7m at 10m base)")
    print("Signal entries   : Stage 1 / Stage 2 / Stage 3 are evaluated independently in report")
    print()

    event_rows: list[dict] = []
    error_rows: list[dict] = []

    for n, rec in enumerate(universe.itertuples(index=False), start=1):
        ticker = str(rec.ticker).zfill(6)
        name = str(rec.name or "")
        print(f"[{n:03d}/{len(universe):03d}] {ticker} {name}")
        try:
            raw = _normalize_ohlcv(load_pykrx(ticker, history_start, forward_end))
            analyzed, events = analyzer.analyze(raw)
            if events.empty:
                continue

            e = events.copy()
            e["date"] = pd.to_datetime(e["date"])
            e = e[(e["date"] >= start) & (e["date"] <= end)]
            e = e[e["action"].astype(str).str.contains("_ENTRY_STAGE_", regex=False)]
            if e.empty:
                continue

            for _, row in e.iterrows():
                action = str(row["action"])
                side = "SHORT" if action.startswith("SHORT_") else "LONG"
                base = {
                    "signal_date": pd.Timestamp(row["date"]),
                    "ticker": ticker,
                    "name": name,
                    "source_rank": int(rec.source_rank),
                    "sort_by": params.sort_by,
                    "side": side,
                    "direction": _direction(action),
                    "stage": int(row.get("stage", 0)),
                    "action": action,
                    "entry_price": float(row["price"]),
                    "entry_amount_krw": float(row.get("amount_krw", np.nan)),
                    "cumulative_invested_krw": float(row.get("cumulative_invested_krw", np.nan)),
                    "weighted_entry_price": float(row.get("weighted_entry_price", np.nan)),
                    "stop_price": row.get("stop_price", np.nan),
                    "reference_target_price": row.get("reference_target_price", np.nan),
                    "risk_capped": bool(row.get("risk_capped", False)),
                }
                event_rows.append(_add_forward_metrics(base, raw, params.forward_bars))
        except Exception as exc:
            error_rows.append({"ticker": ticker, "name": name, "error": repr(exc)})
            print(f"  [WARN] {exc}")
        time.sleep(max(0.0, float(args.request_delay)))

    events_df = pd.DataFrame(event_rows)
    if not events_df.empty:
        events_df = events_df.sort_values(["signal_date", "ticker", "stage"]).reset_index(drop=True)
        events_df["daily_stage_rank"] = (
            events_df.groupby(["signal_date", "side", "stage"])["source_rank"]
            .rank(method="first")
            .astype(int)
        )

    summary_df = _build_summary(events_df, params.forward_bars)
    errors_df = pd.DataFrame(error_rows, columns=["ticker", "name", "error"])

    out_dir = Path(args.output_root) / f"range_{start:%Y%m%d}_{end:%Y%m%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "dynamic_range_events.csv"
    summary_path = out_dir / "dynamic_range_summary.csv"
    universe_path = out_dir / "universe.csv"
    errors_path = out_dir / "errors.csv"
    excel_path = out_dir / "dynamic_range_backtest.xlsx"

    events_df.to_csv(events_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
    errors_df.to_csv(errors_path, index=False, encoding="utf-8-sig")
    _write_excel(excel_path, events_df, summary_df, universe, errors_df)

    print()
    print("=" * 78)
    print("Range backtest finished")
    print("=" * 78)
    print(f"Entry events : {len(events_df):,}")
    print(f"Errors       : {len(errors_df):,}")
    print(f"Saved        : {excel_path}")
    print(f"Saved        : {events_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DynamicChartAnalyzer TOP-N range backtest")
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--top-n", type=int, default=100, help="Universe size; default 100")
    p.add_argument("--sort-by", choices=["market_cap", "trading_value", "volume"], default="market_cap")
    p.add_argument("--forward-bars", type=int, default=60, help="Forward performance trading bars; default 60")
    p.add_argument("--history-days", type=int, default=450, help="Calendar history before start for indicators")
    p.add_argument("--capital", type=float, default=10_000_000, help="Capital in KRW; fixed 1:2:7 split")
    p.add_argument("--risk-cap", action="store_true", help="Enable optional 2%% account-risk cap")
    p.add_argument("--no-stop", action="store_true", help="Disable protective swing stop")
    p.add_argument("--dynamic-rsi", action="store_true", help="Include experimental Dynamic RSI in analyzer")
    p.add_argument("--request-delay", type=float, default=0.05, help="Delay between ticker requests")
    p.add_argument("--output-root", default=str(ROOT / "results"))
    return p


if __name__ == "__main__":
    raise SystemExit(run_range(build_parser().parse_args()))
