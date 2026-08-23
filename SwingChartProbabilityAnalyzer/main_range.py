from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd

from config import DEFAULT_CONFIG, INFO_EXCEL_PATH, RESULT_DIR
from core.backtester import evaluate_forward_returns, evaluate_signal
from core.probability import EmpiricalProbabilityModel
from core.signal_analyzer import SwingSignalAnalyzer
from data.data_provider import PykrxDataProvider
from reporting.range_excel_writer import write_range_workbook
from reporting.range_agent_exporter import export_range_agent_summary
from services.ticker_universe_service import TickerUniverseService
from utils.date_utils import calendar_start_for_history, calendar_end_for_backtest
from utils.logger import get_logger

log = get_logger("SwingRangeAnalysis")


def parse_date_range(text: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    value = str(text).strip().replace(" ", "")
    parts = re.split(r"[~～]", value)
    if len(parts) != 2:
        raise ValueError("날짜 범위는 YYYYMMDD~YYYYMMDD 형식이어야 합니다.")
    start = pd.to_datetime(parts[0], format="%Y%m%d", errors="raise").normalize()
    end = pd.to_datetime(parts[1], format="%Y%m%d", errors="raise").normalize()
    if start > end:
        raise ValueError("시작일이 종료일보다 늦습니다.")
    return start, end


def config_rows(args, cfg) -> list[dict]:
    rows = [{"Parameter": k, "Value": v} for k, v in cfg.to_dict().items()]
    rows.extend(
        [
            {"Parameter": "date_range", "Value": args.date_range},
            {"Parameter": "top_n", "Value": args.top_n},
            {"Parameter": "sort_by", "Value": args.sort_by},
            {"Parameter": "forward_bars", "Value": args.forward_bars},
            {
                "Parameter": "forward_return_note",
                "Value": "D+N은 신호일 다음 N번째 거래봉 종가 기준이며, 미래 데이터는 신호 판정에 사용하지 않음",
            },
        ]
    )
    return rows


def run_range(args) -> int:
    cfg = DEFAULT_CONFIG
    start_ts, end_ts = parse_date_range(args.date_range)

    provider = PykrxDataProvider(use_cache=not args.no_cache)
    universe = TickerUniverseService(args.info_excel).get_universe(args.top_n, args.sort_by, False)

    pmodel = None
    if args.calibration:
        prob_path = Path(args.calibration)
        if prob_path.exists():
            pmodel = EmpiricalProbabilityModel(prob_path, cfg)
        else:
            log.warning("calibration 파일이 없어 확률 컬럼 없이 진행: %s", prob_path)

    analyzer = SwingSignalAnalyzer(cfg, pmodel)

    fetch_start = pd.Timestamp(calendar_start_for_history(start_ts.strftime("%Y-%m-%d"), cfg.history_calendar_days))
    requested_future_end = pd.Timestamp(
        calendar_end_for_backtest(end_ts.strftime("%Y-%m-%d"), max(60, args.forward_bars * 4))
    )
    today = pd.Timestamp.today().normalize()
    fetch_end = min(requested_future_end, today)

    log.info(
        "RANGE %s ~ %s | universe=%d | fetch=%s~%s | forward=%d bars",
        start_ts.date(),
        end_ts.date(),
        len(universe),
        fetch_start.date(),
        fetch_end.date(),
        args.forward_bars,
    )

    rows: list[dict] = []
    candidate_count = 0
    complete_horizon_count = 0
    complete_col = f"Forward_Complete_{args.forward_bars}D"

    for ti, info in enumerate(universe, 1):
        try:
            full = provider.get_ohlcv(
                info.ticker,
                fetch_start.strftime("%Y-%m-%d"),
                fetch_end.strftime("%Y-%m-%d"),
            )
            if full.empty or len(full) < cfg.min_history_bars:
                continue

            eligible_positions = [
                i
                for i, dt in enumerate(full.index)
                if start_ts <= pd.Timestamp(dt).normalize() <= end_ts
            ]

            for i in eligible_positions:
                if i < cfg.min_history_bars - 1:
                    continue

                hist = full.iloc[: i + 1].copy()
                actual_date = hist.index[-1].strftime("%Y-%m-%d")
                result = analyzer.analyze(info.ticker, info.name, actual_date, hist)
                row = result.to_row()
                row["Requested_Range_Start"] = start_ts.strftime("%Y-%m-%d")
                row["Requested_Range_End"] = end_ts.strftime("%Y-%m-%d")

                forward = evaluate_forward_returns(full, i, args.forward_bars)
                row.update(forward)

                event = evaluate_signal(full, i, result, cfg)
                if event is not None:
                    for key in (
                        "Hit_Mid_Before_Stop",
                        "Hit_PriorHigh_Before_Stop",
                        "Hit_Upper_Before_Stop",
                        "Stop_Hit",
                        "First_Event",
                        "Exit_Date",
                    ):
                        row[key] = event.get(key)
                else:
                    row.update(
                        {
                            "Hit_Mid_Before_Stop": float("nan"),
                            "Hit_PriorHigh_Before_Stop": float("nan"),
                            "Hit_Upper_Before_Stop": float("nan"),
                            "Stop_Hit": float("nan"),
                            "First_Event": "",
                            "Exit_Date": "",
                        }
                    )

                rows.append(row)
                if result.status in ("CONFIRMED", "WATCH"):
                    candidate_count += 1
                    if int(forward.get(complete_col, 0)) == 1:
                        complete_horizon_count += 1

            if ti % 10 == 0:
                log.info(
                    "진행 %d/%d | rows=%d | candidates=%d | completeD+%d=%d",
                    ti,
                    len(universe),
                    len(rows),
                    candidate_count,
                    args.forward_bars,
                    complete_horizon_count,
                )
        except Exception as exc:
            log.warning("%s %s range 분석 실패: %s", info.ticker, info.name, exc)

    all_results = pd.DataFrame(rows)
    if all_results.empty:
        log.warning("분석 결과가 없습니다.")
        return 1

    range_key = f"{start_ts.strftime('%Y%m%d')}_{end_ts.strftime('%Y%m%d')}"
    out_dir = RESULT_DIR / f"range_{range_key}"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results.to_csv(out_dir / "range_all_results.csv", index=False, encoding="utf-8-sig")
    candidates = all_results[all_results["Status"].isin(["CONFIRMED", "WATCH"])].copy()
    candidates.to_csv(out_dir / "range_candidates.csv", index=False, encoding="utf-8-sig")

    agent_json, agent_md = export_range_agent_summary(
        candidates,
        out_dir,
        range_start=start_ts.strftime("%Y-%m-%d"),
        range_end=end_ts.strftime("%Y-%m-%d"),
        forward_bars=args.forward_bars,
    )

    workbook = write_range_workbook(
        out_dir / "swing_range_backtest.xlsx",
        all_results,
        config_rows(args, cfg),
        forward_bars=args.forward_bars,
    )

    log.info("완료: %s", out_dir)
    log.info("Excel: %s", workbook)
    log.info("Agent JSON: %s", agent_json)
    log.info("Agent MD  : %s", agent_md)
    log.info("후보=%d | D+%d 완전평가=%d", candidate_count, args.forward_bars, complete_horizon_count)

    if not candidates.empty:
        milestones = [d for d in (5, 10, 20, 40, 60) if d <= args.forward_bars]
        cols = ["Actual_Date", "Ticker", "Name", "Status", "Score"]
        cols += [f"D+{d}_Close_Return_Pct" for d in milestones]
        cols += [f"MFE_{args.forward_bars}D_Pct", f"MAE_{args.forward_bars}D_Pct", "Hit_Upper_Before_Stop"]
        cols = [c for c in cols if c in candidates.columns]
        print(candidates[cols].head(args.print_top).to_string(index=False))

    incomplete = candidates[pd.to_numeric(candidates.get(complete_col, 0), errors="coerce").fillna(0) != 1]
    if not incomplete.empty:
        log.warning(
            "후보 %d건은 종료일 이후 데이터가 부족하여 D+%d 수익률이 비어 있습니다. "
            "해당 거래일 수가 지난 뒤 다시 실행하면 자동으로 채워집니다.",
            len(incomplete),
            args.forward_bars,
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="영상 '전형적인 스윙매매 차트매매의 정석' 규칙 기반 기간 분석 + 향후 N거래일 실제 수익률"
    )
    p.add_argument("--date-range", required=True, help="YYYYMMDD~YYYYMMDD")
    p.add_argument("--info-excel", default=str(INFO_EXCEL_PATH))
    p.add_argument("--top-n", type=int, default=100, help="0=KOSPI_Info.xlsx 일반주 전체")
    p.add_argument("--sort-by", default="market_cap", choices=["market_cap", "trading_value", "volume"])
    p.add_argument("--forward-bars", type=int, default=20, help="사후평가 거래봉 수. 예: 20, 60")
    p.add_argument("--calibration", default="", help="선택: 과거 확률 calibration CSV. 신호 판정에는 영향 없음")
    p.add_argument("--print-top", type=int, default=40)
    p.add_argument("--no-cache", action="store_true")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(run_range(args))
