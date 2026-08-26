from __future__ import annotations

import argparse
from pathlib import Path
import sys
import pandas as pd

from config import DEFAULT_CONFIG, INFO_EXCEL_PATH, RESULT_DIR
from core.backtester import evaluate_signal
from core.probability import EmpiricalProbabilityModel
from core.signal_analyzer import SwingSignalAnalyzer
from data.data_provider import PykrxDataProvider
from reporting.chart_renderer import render_chart
from reporting.excel_writer import write_result_workbook
from reporting.agent_exporter import export_agent_candidates
from services.ticker_universe_service import TickerUniverseService
from utils.date_utils import calendar_start_for_history, calendar_end_for_backtest
from utils.logger import get_logger

log = get_logger()


CANDIDATE_STATUSES = ("STRONG_CONFIRMED", "CONFIRMED", "WATCH")
STATUS_RANK = {"STRONG_CONFIRMED": 0, "CONFIRMED": 1, "WATCH": 2, "REJECTED": 3}


def _config_rows(cfg):
    return [{"Parameter": k, "Value": v} for k,v in cfg.to_dict().items()]


def scan(args) -> int:
    cfg = DEFAULT_CONFIG
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    universe = TickerUniverseService(args.info_excel).get_universe(args.top_n, args.sort_by, False)
    prob_path = Path(args.calibration) if args.calibration else RESULT_DIR / "calibration_events.csv"
    pmodel = EmpiricalProbabilityModel(prob_path if prob_path.exists() else None, cfg)
    analyzer = SwingSignalAnalyzer(cfg, pmodel)
    start = calendar_start_for_history(args.date, cfg.history_calendar_days)
    rows=[]; result_objects=[]; data_map={}
    log.info("SCAN %s | universe=%d | %s~%s", args.date, len(universe), start, args.date)
    for idx, info in enumerate(universe,1):
        try:
            df = provider.get_ohlcv(info.ticker, start, args.date)
            if df.empty:
                continue
            result = analyzer.analyze(info.ticker, info.name, args.date, df)
            rows.append(result.to_row()); result_objects.append(result); data_map[info.ticker]=df
            if idx % 25 == 0:
                log.info("진행 %d/%d", idx, len(universe))
        except Exception as exc:
            log.warning("%s %s 실패: %s", info.ticker, info.name, exc)
    signals = pd.DataFrame(rows)
    if signals.empty:
        log.warning("결과 없음")
        return 1
    # 정렬: STRONG_CONFIRMED > CONFIRMED > WATCH > REJECTED, 이후 확률(있으면) > 점수
    signals["_rank"] = signals["Status"].map(STATUS_RANK).fillna(9)
    probcol="Prob_Upper_Before_Stop"
    if probcol not in signals.columns: signals[probcol]=pd.NA
    signals = signals.sort_values(["_rank", probcol, "Score"], ascending=[True, False, False], na_position="last").drop(columns="_rank")
    out_dir = RESULT_DIR / pd.Timestamp(args.date).strftime("%Y%m%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    signals.to_csv(out_dir/"scan_results.csv", index=False, encoding="utf-8-sig")
    cand = signals[signals["Status"].isin(CANDIDATE_STATUSES)]
    cand.to_csv(out_dir/"candidates.csv", index=False, encoding="utf-8-sig")
    agent_json, agent_md = export_agent_candidates(signals, out_dir, top_n=args.agent_top_n)
    calibration_summary = pd.DataFrame()
    if not pmodel.table.empty:
        numeric_cols=["Hit_Mid_Before_Stop","Hit_PriorHigh_Before_Stop","Hit_Upper_Before_Stop"]
        calibration_summary=(pmodel.table.groupby(["Status","Score_Band"])[numeric_cols]
                             .agg(["count","mean"]).reset_index())
        calibration_summary.columns=["_".join([str(y) for y in x if y]) if isinstance(x,tuple) else x for x in calibration_summary.columns]
    write_result_workbook(out_dir/"swing_candidates.xlsx", signals, _config_rows(cfg), calibration_summary)
    # 상위 차트 생성: STRONG_CONFIRMED를 가장 먼저 그린다.
    selected = [r for r in result_objects if r.status in CANDIDATE_STATUSES]
    selected.sort(key=lambda r: (STATUS_RANK.get(r.status, 9), -r.score))
    for r in selected[:args.charts]:
        render_chart(data_map[r.ticker], r, cfg, out_dir/"charts")
    log.info("완료: %s", out_dir)
    log.info("Agent JSON: %s", agent_json)
    log.info("Agent MD  : %s", agent_md)
    if not cand.empty:
        cols=[c for c in ["Ticker","Name","Status","Score","Prob_Mid_Before_Stop","Prob_PriorHigh_Before_Stop","Prob_Upper_Before_Stop","Channel_Position","Room_To_Upper_Pct"] if c in cand.columns]
        print(cand[cols].head(args.print_top).to_string(index=False))
    return 0


def calibrate(args) -> int:
    cfg = DEFAULT_CONFIG
    provider = PykrxDataProvider(use_cache=not args.no_cache)
    universe = TickerUniverseService(args.info_excel).get_universe(args.top_n, args.sort_by, False)
    analyzer = SwingSignalAnalyzer(cfg, None)
    fetch_start = calendar_start_for_history(args.start, cfg.history_calendar_days)
    fetch_end = calendar_end_for_backtest(args.end, 45)
    events=[]
    log.info("CALIBRATE %s~%s | universe=%d", args.start, args.end, len(universe))
    for ti, info in enumerate(universe,1):
        try:
            full = provider.get_ohlcv(info.ticker, fetch_start, fetch_end)
            if len(full) < cfg.min_history_bars + cfg.backtest_horizon_bars:
                continue
            eligible=[i for i,d in enumerate(full.index) if pd.Timestamp(args.start) <= d <= pd.Timestamp(args.end)]
            last_event_pos = -10**9
            for i in eligible[::max(1,args.step)]:
                if i < cfg.min_history_bars-1 or i+cfg.backtest_horizon_bars >= len(full):
                    continue
                hist=full.iloc[:i+1]
                r=analyzer.analyze(info.ticker, info.name, hist.index[-1].strftime("%Y-%m-%d"), hist)
                if r.status not in CANDIDATE_STATUSES:
                    continue
                if i - last_event_pos < cfg.calibration_cooldown_bars:
                    continue
                ev=evaluate_signal(full,i,r,cfg)
                if ev:
                    events.append(ev)
                    last_event_pos = i
            if ti % 10 == 0:
                log.info("진행 %d/%d | events=%d", ti, len(universe), len(events))
        except Exception as exc:
            log.warning("%s %s calibration 실패: %s", info.ticker, info.name, exc)
    table=pd.DataFrame(events)
    RESULT_DIR.mkdir(parents=True,exist_ok=True)
    out=Path(args.output) if args.output else RESULT_DIR/"calibration_events.csv"
    table.to_csv(out,index=False,encoding="utf-8-sig")
    if not table.empty:
        summary=table.groupby(["Status","Score_Band"])[["Hit_Mid_Before_Stop","Hit_PriorHigh_Before_Stop","Hit_Upper_Before_Stop"]].agg(["count","mean"])
        print(summary.to_string())
    log.info("calibration 저장: %s | events=%d", out, len(table))
    return 0


def explain(args) -> int:
    cfg=DEFAULT_CONFIG
    provider=PykrxDataProvider(use_cache=not args.no_cache)
    uni=TickerUniverseService(args.info_excel).load_universe_df()
    row=uni[uni["Ticker"].astype(str).str.zfill(6)==args.ticker.zfill(6)]
    name=str(row.iloc[0]["Name"]) if not row.empty else args.ticker
    start=calendar_start_for_history(args.date,cfg.history_calendar_days)
    df=provider.get_ohlcv(args.ticker.zfill(6),start,args.date)
    p=EmpiricalProbabilityModel(RESULT_DIR/"calibration_events.csv",cfg)
    r=SwingSignalAnalyzer(cfg,p).analyze(args.ticker.zfill(6),name,args.date,df)
    print(pd.Series(r.to_row()).to_string())
    path=render_chart(df,r,cfg,RESULT_DIR/"explain")
    if path: print(f"chart={path}")
    return 0


def build_parser():
    p=argparse.ArgumentParser(description="영상 '전형적인 스윙매매 차트매매의 정석' 규칙 기반 종목 선별기")
    sub=p.add_subparsers(dest="cmd",required=True)
    common=argparse.ArgumentParser(add_help=False)
    common.add_argument("--info-excel",default=str(INFO_EXCEL_PATH))
    common.add_argument("--no-cache",action="store_true")
    common.add_argument("--sort-by",default="market_cap",choices=["market_cap","trading_value","volume"])
    s=sub.add_parser("scan",parents=[common])
    s.add_argument("--date",default=pd.Timestamp.today().strftime("%Y-%m-%d"),help="YYYY-MM-DD; 생략 시 오늘")
    s.add_argument("--top-n",type=int,default=0,help="0=Excel 내 전체 일반주")
    s.add_argument("--calibration",default="")
    s.add_argument("--charts",type=int,default=20)
    s.add_argument("--print-top",type=int,default=30)
    s.add_argument("--agent-top-n",type=int,default=30,help="서브에이전트 입력 후보 최대 개수")
    s.set_defaults(func=scan)
    c=sub.add_parser("calibrate",parents=[common])
    c.add_argument("--start",required=True); c.add_argument("--end",required=True)
    c.add_argument("--top-n",type=int,default=200)
    c.add_argument("--step",type=int,default=DEFAULT_CONFIG.calibration_step_bars)
    c.add_argument("--output",default="")
    c.set_defaults(func=calibrate)
    e=sub.add_parser("explain",parents=[common])
    e.add_argument("--ticker",required=True); e.add_argument("--date",required=True)
    e.set_defaults(func=explain)
    return p


if __name__ == "__main__":
    args=build_parser().parse_args()
    raise SystemExit(args.func(args))
