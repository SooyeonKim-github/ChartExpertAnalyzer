from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MarketData import (  # noqa: E402
    ExcelUniverseService,
    build_market_close_history,
    build_snapshot_universe,
    get_market_data_service,
    get_market_index_ohlcv,
)


class TrendFollowingDataProvider:
    def __init__(self, cfg: dict, base_dir: str | Path, universe_xlsx: str | Path | None = None) -> None:
        self.cfg = cfg
        self.base_dir = Path(base_dir)
        self.market_data = get_market_data_service()
        self.universe_xlsx = self._resolve_universe_xlsx(universe_xlsx)
        self._history_cache: dict[str, pd.DataFrame] = {}
        self._index_cache: dict[str, pd.DataFrame] = {}
        self._breadth_source_cache: dict[str, tuple[pd.DataFrame, dict]] = {}
        self._candidate_infos: list = []
        self._candidate_top_n: int | None = None
        self.universe_source_meta: dict = {}

    def _resolve_universe_xlsx(self, explicit: str | Path | None) -> Path:
        candidates=[]
        if explicit: candidates.append(Path(explicit))
        env_path=os.environ.get("LIQUIDITY_UNIVERSE_XLSX","").strip()
        if env_path: candidates.append(Path(env_path))
        candidates.extend([self.base_dir / "KOSPI_Info.xlsx", REPO_ROOT / "KJBChartAnalyzer" / "KOSPI_Info.xlsx"])
        for path in candidates:
            if path.exists(): return path
        raise FileNotFoundError("Universe Excel not found. Use --universe-xlsx or LIQUIDITY_UNIVERSE_XLSX.\n" + "\n".join(f"- {p}" for p in candidates))

    @staticmethod
    def _normalize_daily(df: pd.DataFrame) -> pd.DataFrame:
        columns=["open","high","low","close","volume","trading_value"]
        if df is None or df.empty: return pd.DataFrame(columns=columns)
        out=df.rename(columns={"Open":"open","High":"high","Low":"low","Close":"close","Volume":"volume","Trading_Value":"trading_value","시가":"open","고가":"high","저가":"low","종가":"close","거래량":"volume","거래대금":"trading_value"}).copy()
        for col in columns:
            if col not in out.columns: out[col]=0.0
            out[col]=pd.to_numeric(out[col],errors="coerce")
        out.index=pd.to_datetime(out.index,errors="coerce")
        out=out[~out.index.isna()]
        return out[~out.index.duplicated(keep="last")].sort_index()[columns].dropna(subset=["close"])

    def resolve_scan_date(self, requested: str | None = None) -> str:
        return self.market_data.resolve_trading_date(requested)

    def _candidate_pool_size(self, top_n: int) -> int:
        return max(int(top_n), int(top_n) * max(1,int(self.cfg["universe"].get("candidate_multiplier",3))))

    def _load_candidate_infos(self, top_n: int) -> list:
        if self._candidate_infos and self._candidate_top_n == top_n: return self._candidate_infos
        service=ExcelUniverseService(self.universe_xlsx)
        self._candidate_infos=service.get_universe(top_n=self._candidate_pool_size(top_n),sort_by="trading_value",include_etf=False,markets=("KOSPI","KOSDAQ"))
        self._candidate_top_n=top_n
        return self._candidate_infos

    def _load_history_for(self, ticker: str, market: str, scan_date: str) -> pd.DataFrame:
        code=str(ticker).zfill(6)
        if code in self._history_cache: return self._history_cache[code]
        end=pd.Timestamp(scan_date).normalize(); start=end-pd.Timedelta(days=int(self.cfg["data"].get("history_days",520)))
        bars=self.market_data.get_ohlcv(code,start,end,market_hint=str(market).upper(),allow_etf=False)
        bars=self._normalize_daily(bars); self._history_cache[code]=bars; return bars

    def _snapshot_candidate_frame(self, scan_date: str, top_n: int) -> pd.DataFrame:
        frame,meta=build_snapshot_universe(scan_date,top_n=self._candidate_pool_size(top_n),markets=("KOSPI","KOSDAQ"),info_excel=self.universe_xlsx,service=self.market_data,require_all_markets=True)
        self.universe_source_meta=dict(meta)
        print(f"[INFO] Trend universe source=POINT_IN_TIME_ALL_MARKET_SNAPSHOT | candidates={len(frame):,}")
        return frame

    def _excel_candidate_frame(self, top_n: int) -> pd.DataFrame:
        infos=self._load_candidate_infos(top_n)
        frame=pd.DataFrame([{"ticker":str(i.ticker).zfill(6),"name":str(i.name),"market":str(i.market).upper(),"source_rank":int(i.source_rank or 0)} for i in infos])
        counts=frame["market"].value_counts().to_dict() if not frame.empty else {}
        self.universe_source_meta={"source_mode":"CURRENT_EXCEL_UNIVERSE_FALLBACK","membership_mode":"CURRENT_EXCEL_UNIVERSE","markets_loaded":sorted(counts),"row_count":int(len(frame))}
        print(f"[WARN] Trend universe snapshot unavailable -> current Excel fallback | KOSPI={counts.get('KOSPI',0)} | KOSDAQ={counts.get('KOSDAQ',0)}")
        return frame

    def build_universe(self, scan_date: str, top_n: int | None = None) -> pd.DataFrame:
        ucfg=self.cfg["universe"]; n=int(top_n or ucfg.get("top_n",100)); target=pd.Timestamp(scan_date).normalize()
        if bool(ucfg.get("snapshot_primary",True)):
            try: candidates=self._snapshot_candidate_frame(scan_date,n)
            except Exception as exc:
                print(f"[WARN] Point-in-time KOSPI+KOSDAQ universe failed: {type(exc).__name__}: {exc}"); candidates=self._excel_candidate_frame(n)
        else: candidates=self._excel_candidate_frame(n)
        rows=[]
        for _,candidate in candidates.iterrows():
            ticker=str(candidate.get("ticker","")).zfill(6); market=str(candidate.get("market","")).upper()
            if market not in {"KOSPI","KOSDAQ"}: continue
            try:
                hist=self._load_history_for(ticker,market,scan_date); hist=hist[hist.index.normalize()<=target]
                if hist.empty or pd.Timestamp(hist.index[-1]).normalize()!=target: continue
                last=hist.iloc[-1]; close=float(last["close"]); volume=float(last.get("volume",0.0) or 0.0); trading_value=float(last.get("trading_value",0.0) or 0.0)
                if trading_value<=0 and close>0 and volume>0: trading_value=close*volume
                rows.append({"ticker":ticker,"name":str(candidate.get("name",ticker)),"market":market,"close":close,"trading_value":trading_value})
            except Exception: continue
        df=pd.DataFrame(rows)
        if df.empty: raise RuntimeError(f"Trend-following universe is empty for {scan_date}")
        df["close"]=pd.to_numeric(df["close"],errors="coerce"); df["trading_value"]=pd.to_numeric(df["trading_value"],errors="coerce")
        df=df[(df["close"]>=float(ucfg.get("min_price",0))) & df["trading_value"].fillna(0).gt(0)].copy()
        if ucfg.get("exclude_spac",True): df=df[~df["name"].str.contains("스팩",na=False)].copy()
        df=df.sort_values("trading_value",ascending=False).head(n).copy(); df["trading_value_rank"]=range(1,len(df)+1)
        counts=df["market"].value_counts().to_dict(); print(f"[INFO] Trend universe final | total={len(df)} | KOSPI={counts.get('KOSPI',0)} | KOSDAQ={counts.get('KOSDAQ',0)}")
        return df.set_index("ticker")

    def get_daily(self, ticker: str, scan_date: str) -> pd.DataFrame:
        code=str(ticker).zfill(6); cached=self._history_cache.get(code)
        if cached is not None:
            target=pd.Timestamp(scan_date).normalize(); return cached[cached.index.normalize()<=target].copy()
        end=pd.Timestamp(scan_date).normalize(); start=end-pd.Timedelta(days=int(self.cfg["data"].get("history_days",520)))
        return self._normalize_daily(self.market_data.get_ohlcv(code,start,end,allow_etf=False))

    def get_market_index(self, market: str, scan_date: str) -> pd.DataFrame:
        market_key=str(market).upper()
        if market_key in self._index_cache: return self._index_cache[market_key].copy()
        history_days=max(int(self.cfg["data"].get("history_days",520)),int(self.cfg.get("market_regime",{}).get("history_days",520)))
        end=pd.Timestamp(scan_date).normalize(); start=end-pd.Timedelta(days=history_days)
        out=self._normalize_daily(get_market_index_ohlcv(market_key,start,end,service=self.market_data)); out=out[out.index.normalize()<=end].copy(); self._index_cache[market_key]=out; return out.copy()

    def get_market_breadth_source(self, market: str, scan_date: str) -> tuple[pd.DataFrame,dict]:
        market_key=str(market).upper(); cache_key=f"{market_key}:{scan_date}"
        if cache_key in self._breadth_source_cache:
            frame,meta=self._breadth_source_cache[cache_key]; return frame.copy(),dict(meta)
        bcfg=self.cfg.get("market_regime",{}).get("breadth_52w",{})
        if not bool(bcfg.get("enabled",True)):
            meta={"expected_dates":0,"loaded_dates":0,"failed_dates":0,"source_mode":"DISABLED","membership_mode":"DISABLED","ticker_count":0,"failed_tickers":0}; return pd.DataFrame(columns=["date","ticker","close"]),meta
        required=max(int(bcfg.get("lookback_sessions",252))+int(bcfg.get("long_window",20)),int(bcfg.get("lookback_sessions",252)))
        index_df=self.get_market_index(market_key,scan_date); dates=pd.DatetimeIndex(pd.to_datetime(index_df.index,errors="coerce")).dropna(); end=pd.Timestamp(scan_date).normalize(); dates=dates[dates.normalize()<=end]; dates=pd.DatetimeIndex(sorted(set(pd.Timestamp(x).normalize() for x in dates)))
        if len(dates)>required: dates=dates[-required:]
        if len(dates)==0: raise RuntimeError(f"{market_key} breadth calendar is empty")
        source,meta=build_market_close_history(dates[0],dates[-1],market_key,info_excel=self.universe_xlsx,service=self.market_data,snapshot_fail_fast=int(bcfg.get("snapshot_fail_fast",2)),allow_current_universe_fallback=bool(bcfg.get("allow_current_universe_fallback",True)))
        allowed={pd.Timestamp(x).normalize() for x in dates}; source=source[pd.to_datetime(source["date"],errors="coerce").dt.normalize().isin(allowed)].copy(); meta=dict(meta); meta["expected_dates"]=int(len(dates)); meta["loaded_dates"]=int(pd.to_datetime(source["date"],errors="coerce").dt.normalize().nunique()); meta["failed_dates"]=max(0,meta["expected_dates"]-meta["loaded_dates"])
        print(f"[INFO] {market_key} breadth source={meta.get('source_mode')} | membership={meta.get('membership_mode')} | dates={meta.get('loaded_dates')}/{meta.get('expected_dates')} | tickers={meta.get('ticker_count',0)}")
        self._breadth_source_cache[cache_key]=(source.copy(),dict(meta)); return source,meta
