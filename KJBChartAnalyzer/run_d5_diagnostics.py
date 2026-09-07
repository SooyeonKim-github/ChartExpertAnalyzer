from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from chartsel.analysis.overextension import evaluate_overextension  # noqa: E402
from chartsel.config import load_config  # noqa: E402
from chartsel.selection.confirmation import classify_confirmation_values  # noqa: E402


D5 = 'D+5'


def _latest_range_file() -> Path:
    files = list((BASE_DIR / 'results').glob('range_*/chart_range_events.csv'))
    if not files:
        raise FileNotFoundError('chart_range_events.csv가 없습니다. 먼저 KJB range를 실행하세요.')
    return max(files, key=lambda p: (p.parent.name, p.stat().st_mtime))


def _resolve(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else BASE_DIR / p


def _normalize_market(value) -> str:
    text = str(value or '').strip().upper()
    if 'KOSDAQ' in text or text in {'KQ', '^KQ11', '2001'}:
        return 'KOSDAQ'
    if 'KOSPI' in text or text in {'KS', '^KS11', '1001'}:
        return 'KOSPI'
    return text


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors='coerce')


def _build_market_context(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    market = pd.read_csv(path, encoding='utf-8-sig')
    if market.empty or 'date' not in market.columns or 'market' not in market.columns:
        return pd.DataFrame()
    market = market.copy()
    market['date'] = pd.to_datetime(market['date'], errors='coerce').dt.normalize()
    market['market'] = market['market'].map(_normalize_market)
    market['index_close'] = _num(market, 'index_close')
    market = market.sort_values(['market', 'date']).reset_index(drop=True)
    market['index_forward_return_5d'] = (
        market.groupby('market', sort=False)['index_close'].shift(-5) / market['index_close'] - 1.0
    )
    keep = [
        'date', 'market', 'index_forward_return_5d',
        'breadth_stock_count', 'breadth_above_ma20_ratio', 'breadth_above_ma60_ratio',
        'breadth_positive_5d_ratio', 'breadth_positive_20d_ratio',
        'index_return_5d', 'index_return_20d', 'index_ma20_gap', 'index_ma60_gap',
    ]
    return market[[c for c in keep if c in market.columns]].copy()


def _enrich_events(events: pd.DataFrame, cfg: dict, market_ctx: pd.DataFrame) -> pd.DataFrame:
    required = [
        'signal_date', 'selection_score', 'technical_score', 'timing_score',
        'risk_score', 'leader_score', 'relative_strength_score', 'chase_risk', D5,
    ]
    missing = [c for c in required if c not in events.columns]
    if missing:
        raise ValueError(f'D+5 진단에 필요한 컬럼이 없습니다: {missing}')

    out = events.copy()
    out['signal_date'] = pd.to_datetime(out['signal_date'], errors='coerce').dt.normalize()
    if 'market' in out.columns:
        out['market'] = out['market'].map(_normalize_market)

    d5_scores: list[float] = []
    d5_grades: list[str] = []
    penalties: list[float] = []
    component_rows: list[dict] = []
    statuses: list[str] = []

    for r in out.itertuples(index=False):
        row = r._asdict()
        over = evaluate_overextension(
            selection_score=row['selection_score'],
            leader_score=row['leader_score'],
            relative_strength_score=row['relative_strength_score'],
            chase_risk=row['chase_risk'],
            cfg=cfg.get('overextension', {}),
        )
        d5_scores.append(over['d5_score'])
        d5_grades.append(over['d5_grade'])
        penalties.append(over['penalty'])
        component_rows.append(over['components'])
        statuses.append(classify_confirmation_values(
            selection_score=row['selection_score'],
            technical_score=row['technical_score'],
            timing_score=row['timing_score'],
            risk_score=row['risk_score'],
            leader_score=row['leader_score'],
            relative_strength_score=row['relative_strength_score'],
            chase_risk=row['chase_risk'],
            d5_score=over['d5_score'],
            cfg=cfg,
        ))

    out['d5_score'] = d5_scores
    out['d5_grade'] = d5_grades
    out['overextension_penalty'] = penalties
    components = pd.DataFrame(component_rows, index=out.index)
    for key in ['selection', 'leader', 'relative_strength', 'chase']:
        out[f'overext_{key}'] = pd.to_numeric(components.get(key, 0.0), errors='coerce').fillna(0.0)
    out['Status'] = statuses

    out['daily_raw_rank'] = out.groupby('signal_date')['selection_score'].rank(method='first', ascending=False).astype('Int64')
    out['daily_d5_rank'] = out.groupby('signal_date')['d5_score'].rank(method='first', ascending=False).astype('Int64')

    if not market_ctx.empty and 'market' in out.columns:
        out = out.merge(
            market_ctx,
            left_on=['signal_date', 'market'],
            right_on=['date', 'market'],
            how='left',
        )
        out = out.drop(columns=['date'], errors='ignore')
    else:
        out['index_forward_return_5d'] = np.nan

    out[D5] = _num(out, D5)
    out['d5_excess_return'] = out[D5] - _num(out, 'index_forward_return_5d')
    return out


def _summary(frame: pd.DataFrame, dimension: str, bucket: str) -> dict:
    ret = _num(frame, D5).dropna()
    excess = _num(frame, 'd5_excess_return').dropna()
    penalty = _num(frame, 'overextension_penalty').dropna()
    d5score = _num(frame, 'd5_score').dropna()
    return {
        'dimension': dimension,
        'bucket': str(bucket),
        'valid_count': int(ret.size),
        'unique_dates': int(frame.loc[_num(frame, D5).notna(), 'signal_date'].nunique()) if 'signal_date' in frame.columns else 0,
        'avg_return': float(ret.mean()) if len(ret) else np.nan,
        'median_return': float(ret.median()) if len(ret) else np.nan,
        'p25_return': float(ret.quantile(0.25)) if len(ret) else np.nan,
        'win_rate': float((ret > 0).mean()) if len(ret) else np.nan,
        'avg_excess_return': float(excess.mean()) if len(excess) else np.nan,
        'median_excess_return': float(excess.median()) if len(excess) else np.nan,
        'excess_win_rate': float((excess > 0).mean()) if len(excess) else np.nan,
        'avg_d5_score': float(d5score.mean()) if len(d5score) else np.nan,
        'avg_overextension_penalty': float(penalty.mean()) if len(penalty) else np.nan,
    }


def _numeric_buckets(frame: pd.DataFrame, column: str, edges: list[float], labels: list[str]) -> list[dict]:
    if column not in frame.columns:
        return []
    x = _num(frame, column)
    buckets = pd.cut(x, bins=edges, labels=labels, right=False, include_lowest=True)
    rows: list[dict] = []
    for label in labels:
        mask = buckets.astype('object').eq(label)
        if mask.any():
            rows.append(_summary(frame.loc[mask], column, label))
    return rows


def build_bucket_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    rows = [_summary(frame, 'ALL', 'ALL')]

    for col in ['Status', 'market_regime', 'market']:
        if col in frame.columns:
            for value, sub in frame.groupby(col, dropna=False):
                rows.append(_summary(sub, col, value))

    specs = [
        ('selection_score', [-np.inf, 60, 70, 75, 80, 85, 90, np.inf], ['<60', '60-70', '70-75', '75-80', '80-85', '85-90', '90+']),
        ('d5_score', [-np.inf, 60, 70, 75, 80, 85, 90, np.inf], ['<60', '60-70', '70-75', '75-80', '80-85', '85-90', '90+']),
        ('timing_score', [-np.inf, 60, 65, 70, 75, 80, 85, 90, np.inf], ['<60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90+']),
        ('relative_strength_score', [-np.inf, 40, 50, 60, 70, 80, 90, 95, np.inf], ['<40', '40-50', '50-60', '60-70', '70-80', '80-90', '90-95', '95+']),
        ('leader_score', [-np.inf, 60, 70, 80, 85, 90, np.inf], ['<60', '60-70', '70-80', '80-85', '85-90', '90+']),
        ('sector_leader_score', [-np.inf, 60, 70, 80, 85, 90, np.inf], ['<60', '60-70', '70-80', '80-85', '85-90', '90+']),
        ('overextension_penalty', [-0.001, 0.001, 2, 5, 8, 12, 20, np.inf], ['0', '0-2', '2-5', '5-8', '8-12', '12-20', '20+']),
        ('breadth_above_ma20_ratio', [-np.inf, 0.3, 0.4, 0.5, 0.6, 0.7, np.inf], ['<30%', '30-40%', '40-50%', '50-60%', '60-70%', '70%+']),
        ('breadth_above_ma60_ratio', [-np.inf, 0.3, 0.4, 0.5, 0.6, 0.7, np.inf], ['<30%', '30-40%', '40-50%', '50-60%', '60-70%', '70%+']),
    ]
    for column, edges, labels in specs:
        rows.extend(_numeric_buckets(frame, column, edges, labels))
    return pd.DataFrame(rows)


def build_topn_diagnostics(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for cohort, base in [('ALL', frame), ('CONFIRMED', frame[frame['Status'].eq('CONFIRMED')])]:
        if base.empty:
            continue
        for ranking, score_col in [('RAW_SELECTION', 'selection_score'), ('D5_SCORE', 'd5_score')]:
            ranked = base.copy()
            ranked['_rank'] = ranked.groupby('signal_date')[score_col].rank(method='first', ascending=False)
            for n in [3, 5, 10, 20]:
                sub = ranked[ranked['_rank'] <= n]
                row = _summary(sub, 'TopN', f'{cohort}_{ranking}_TOP{n}')
                row['cohort'] = cohort
                row['ranking'] = ranking
                row['top_n'] = n
                rows.append(row)
    return pd.DataFrame(rows)


def _fmt_pct(value) -> str:
    return '-' if pd.isna(value) else f'{float(value) * 100:.2f}%'


def main() -> None:
    p = argparse.ArgumentParser(description='KJB D+5 diagnostics + overextension report')
    p.add_argument('--range-file')
    p.add_argument('--config', default='config/default.yaml')
    p.add_argument('--market-file')
    p.add_argument('--out-dir')
    args = p.parse_args()

    range_file = _resolve(args.range_file, _latest_range_file())
    out_dir = _resolve(args.out_dir, range_file.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = _resolve(args.config, BASE_DIR / 'config/default.yaml')
    cfg = load_config(str(config_path))
    market_file = _resolve(args.market_file, range_file.parent / 'market_regime_daily.csv')

    events = pd.read_csv(range_file, encoding='utf-8-sig', dtype={'ticker': str})
    market_ctx = _build_market_context(market_file)
    enriched = _enrich_events(events, cfg, market_ctx)
    diagnostics = build_bucket_diagnostics(enriched)
    topn = build_topn_diagnostics(enriched)
    status = diagnostics[diagnostics['dimension'].isin(['ALL', 'Status'])].copy()

    events_out = out_dir / 'chart_range_events_d5.csv'
    diag_out = out_dir / 'd5_diagnostics_buckets.csv'
    topn_out = out_dir / 'd5_diagnostics_topn.csv'
    status_out = out_dir / 'd5_status_summary.csv'
    enriched.to_csv(events_out, index=False, encoding='utf-8-sig')
    diagnostics.to_csv(diag_out, index=False, encoding='utf-8-sig')
    topn.to_csv(topn_out, index=False, encoding='utf-8-sig')
    status.to_csv(status_out, index=False, encoding='utf-8-sig')

    xlsx = range_file.parent / 'chart_range_backtest.xlsx'
    if xlsx.exists():
        try:
            with pd.ExcelWriter(xlsx, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                status.to_excel(writer, sheet_name='D5Status', index=False)
                diagnostics.to_excel(writer, sheet_name='D5진단', index=False)
                topn.to_excel(writer, sheet_name='D5TopN', index=False)
        except Exception as exc:
            print(f'[WARN] D+5 Excel 진단 시트 저장 실패: {exc}')

    print('\n[D+5 STATUS 진단]')
    view = status[['dimension', 'bucket', 'valid_count', 'avg_return', 'median_return', 'win_rate', 'avg_excess_return']].copy()
    for c in ['avg_return', 'median_return', 'win_rate', 'avg_excess_return']:
        view[c] = view[c].map(_fmt_pct)
    print(view.to_string(index=False))

    print('\n[D+5 TOP5 비교]')
    top5 = topn[topn['top_n'].eq(5)].copy()
    if not top5.empty:
        view = top5[['bucket', 'valid_count', 'avg_return', 'median_return', 'win_rate', 'avg_excess_return']].copy()
        for c in ['avg_return', 'median_return', 'win_rate', 'avg_excess_return']:
            view[c] = view[c].map(_fmt_pct)
        print(view.to_string(index=False))

    print('\n[완료]')
    print('D5 Events :', events_out)
    print('D5 Buckets:', diag_out)
    print('D5 TopN   :', topn_out)
    print('D5 Status :', status_out)
    if market_ctx.empty:
        print('[주의] market_regime_daily.csv가 없어 KOSPI/KOSDAQ 대비 D+5 초과수익률은 비어 있습니다.')


if __name__ == '__main__':
    main()
