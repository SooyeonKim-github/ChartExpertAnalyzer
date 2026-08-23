from __future__ import annotations

import html
from pathlib import Path

import pandas as pd

from .range_engine import key_horizon_summary


def save_range_backtest_excel(
    events: pd.DataFrame,
    summary: pd.DataFrame,
    universe: pd.DataFrame,
    errors: pd.DataFrame,
    out_path: str | Path,
    params: dict,
) -> Path:
    """사용자 PC에서 실행되는 백테스트 결과 엑셀 생성기."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    key = key_horizon_summary(summary)
    param_rows = pd.DataFrame([{'항목': k, '값': v} for k, v in params.items()])

    with pd.ExcelWriter(p, engine='openpyxl') as writer:
        # 요약 상단에 파라미터와 핵심 D+n 통계를 배치한다.
        param_rows.to_excel(writer, sheet_name='요약', index=False, startrow=1)
        key.to_excel(writer, sheet_name='요약', index=False, startrow=len(param_rows) + 4)
        summary.to_excel(writer, sheet_name='D+1~60통계', index=False)
        events.to_excel(writer, sheet_name='신호상세', index=False)
        universe.to_excel(writer, sheet_name='Universe', index=False)
        if errors is not None and not errors.empty:
            errors.to_excel(writer, sheet_name='오류', index=False)

        wb = writer.book
        ws = wb['요약']
        ws['A1'] = '차트 신호 기간 백테스트 요약'
        ws['A1'].font = ws['A1'].font.copy(bold=True, size=14)

        header_fill = '1F4E78'
        header_font = 'FFFFFF'
        for ws in wb.worksheets:
            ws.freeze_panes = 'A2' if ws.title != '요약' else 'A2'
            for row in ws.iter_rows():
                for cell in row:
                    if cell.row in (1, len(param_rows) + 5) and ws.title == '요약':
                        cell.font = cell.font.copy(bold=True, color=header_font)
                        cell.fill = cell.fill.copy(fill_type='solid', fgColor=header_fill)
            if ws.title != '요약':
                for cell in ws[1]:
                    cell.font = cell.font.copy(bold=True, color=header_font)
                    cell.fill = cell.fill.copy(fill_type='solid', fgColor=header_fill)
            ws.auto_filter.ref = ws.dimensions if ws.max_row > 1 else None

        # % 형식: 신호상세 D+n/MFE/MAE, 통계 수익률/승률
        if '신호상세' in wb.sheetnames and not events.empty:
            ws = wb['신호상세']
            headers = {c.value: c.column for c in ws[1]}
            pct_names = [c for c in events.columns if c.startswith('D+')]
            pct_names += [c for c in events.columns if c.startswith('MFE_') or c.startswith('MAE_') or c.startswith('max_close_return') or c.startswith('min_close_return')]
            for name in pct_names:
                col = headers.get(name)
                if col:
                    for r in range(2, ws.max_row + 1):
                        ws.cell(r, col).number_format = '0.00%'
            if headers.get('signal_date'):
                for r in range(2, ws.max_row + 1):
                    ws.cell(r, headers['signal_date']).number_format = 'yyyy-mm-dd'

        for sheet_name in ('D+1~60통계', '요약'):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value in ('avg_return', 'median_return', 'win_rate', 'loss_rate', 'std_return', 'best_return', 'worst_return'):
                        col = cell.column
                        for rr in range(cell.row + 1, ws.max_row + 1):
                            ws.cell(rr, col).number_format = '0.00%'

        # 가독성 중심 폭 제한
        widths = {
            'A': 14, 'B': 10, 'C': 12, 'D': 18, 'E': 10, 'F': 10, 'G': 16, 'H': 13,
            'I': 13, 'J': 10, 'K': 13, 'L': 10, 'M': 13, 'N': 10, 'O': 12, 'P': 11,
        }
        for ws in wb.worksheets:
            for col, width in widths.items():
                ws.column_dimensions[col].width = width
            for col_idx in range(17, min(ws.max_column, 32) + 1):
                ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = 15
            if ws.title == '신호상세':
                for col_idx in range(33, ws.max_column + 1):
                    ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = 11

    return p


def save_range_backtest_html(events: pd.DataFrame, summary: pd.DataFrame, out_path: str | Path, params: dict) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    key = key_horizon_summary(summary)

    def pct(v):
        return '-' if pd.isna(v) else f'{float(v)*100:.2f}%'

    cards = []
    for _, r in key.iterrows():
        cards.append(f'''<div class="card"><div class="label">{html.escape(str(r['horizon']))}</div>
        <div class="value">{pct(r['avg_return'])}</div><div class="sub">승률 {pct(r['win_rate'])} · n={int(r['valid_count'])}</div></div>''')

    top = events.sort_values(['selection_score','timing_score','technical_score'], ascending=False).head(50) if not events.empty else events
    table_html = top[['signal_date','daily_rank','ticker','name','selection_score','technical_score','timing_score','risk_score','entry_status','D+5','D+20','D+60']].to_html(
        index=False, escape=True, classes='tbl', border=0,
        formatters={
            'D+5': pct, 'D+20': pct, 'D+60': pct,
            'selection_score': lambda v:f'{v:.1f}', 'technical_score':lambda v:f'{v:.1f}',
            'timing_score':lambda v:f'{v:.1f}', 'risk_score':lambda v:f'{v:.1f}',
        }
    ) if not top.empty else '<p>조건 충족 신호가 없습니다.</p>'

    param_text = ' · '.join(f'{html.escape(str(k))}: {html.escape(str(v))}' for k,v in params.items())
    doc = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>기간 백테스트</title>
<style>
body{{font-family:Arial,'Malgun Gothic',sans-serif;background:#f5f7fb;color:#172033;margin:0;padding:28px}}
.wrap{{max-width:1500px;margin:auto}} h1{{margin:0 0 8px}} .muted{{color:#667085;font-size:13px;margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(6,minmax(150px,1fr));gap:12px;margin:18px 0}}
.card{{background:white;border:1px solid #e4e7ec;border-radius:14px;padding:16px;box-shadow:0 3px 12px rgba(16,24,40,.04)}}
.label{{color:#667085;font-size:13px}} .value{{font-size:25px;font-weight:700;margin:6px 0}} .sub{{font-size:12px;color:#667085}}
.panel{{background:white;border:1px solid #e4e7ec;border-radius:14px;padding:18px;overflow:auto}}
.tbl{{border-collapse:collapse;width:100%;font-size:12px}} .tbl th{{background:#163a5f;color:white;position:sticky;top:0;padding:8px}}
.tbl td{{padding:7px;border-bottom:1px solid #eef1f5;white-space:nowrap;text-align:right}} .tbl td:nth-child(1),.tbl td:nth-child(3),.tbl td:nth-child(4),.tbl td:nth-child(9){{text-align:left}}
@media(max-width:900px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap"><h1>차트 신호 기간 백테스트</h1><div class="muted">{param_text}</div>
<div class="cards">{''.join(cards)}</div><div class="panel"><h2>선별 신호 TOP 50</h2>{table_html}</div></div></body></html>'''
    p.write_text(doc, encoding='utf-8')
    return p
