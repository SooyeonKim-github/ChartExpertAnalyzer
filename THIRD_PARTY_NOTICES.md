# Third-Party Notices

## TraderMonty / claude-trading-skills

Several methodology-oriented Claude Skills in this repository were adapted for Korean equities from ideas and workflows in:

- Project: `tradermonty/claude-trading-skills`
- Source: https://github.com/tradermonty/claude-trading-skills
- License: MIT License
- Copyright: Copyright (c) 2026 TraderMonty

The ChartExpertAnalyzer adaptations do **not** copy US-market-specific data dependencies such as FMP, SEC 13F, FINVIZ-only workflows, or S&P-specific thresholds unless explicitly documented. They are rewritten around KOSPI/KOSDAQ Analyzer outputs.

Adapted concepts currently include:

- Technical Analyst → `technical-chart-analysis`
- Sector Analyst → `kr-sector-leadership`
- Institutional Flow Tracker → `kr-investor-flow`
- Market Breadth Analyzer → `kr-market-breadth`
- Backtest Expert → `backtest-robustness`
- Data Quality Checker → `candidate-data-quality`
- Position Sizer → `position-sizing`
- Skill Integration Tester → `workflow-integration-test`
- Dual-Axis Skill Reviewer / Self-Improvement Loop → `dual-axis-quality-review`, `self-improvement-loop`, and `scripts/run_self_improvement.py`

### MIT License Notice

Permission is hereby granted, free of charge, to any person obtaining a copy of the Software and associated documentation files, to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies, subject to inclusion of the copyright and permission notice.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
