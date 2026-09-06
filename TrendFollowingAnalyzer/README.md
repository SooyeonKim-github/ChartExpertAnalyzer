# TrendFollowingAnalyzer

추세추종 강의의 매매 의사결정을 독립 Analyzer로 구현하는 프로젝트입니다.

## 개발 로드맵

1. 프로젝트 뼈대
2. MA50 / MA150
3. Stage Detector
4. Market Regime
5. Relative Strength
6. Prior Advance
7. Generic Base Detector
8. Volume Contraction
9. Breakout Detector
10. V1 Backtest
11. VCP
12. Cup With Handle
13. Initial Stop
14. High Volume Reversal
15. MA50 / MA150 Trend Exit
16. Score
17. Threshold Optimizer
18. Ablation Backtest

현재 구현 범위는 **1~3번**입니다.

## 현재 Stage 규칙

강의의 30주 이동평균선을 일봉의 약 150거래일 이동평균선으로 근사합니다.

- `STAGE_2`: 종가가 MA150 위 + MA150 기울기가 충분히 상승
- `STAGE_4`: 종가가 MA150 아래 + MA150 기울기가 충분히 하락
- `STAGE_1`: 최근 확정 추세가 Stage 4였고 현재 Stage 2/4 조건이 아닌 전환·횡보 구간
- `STAGE_3`: 최근 확정 추세가 Stage 2였고 현재 Stage 2/4 조건이 아닌 전환·횡보 구간
- `INSUFFICIENT`: MA150/기울기 계산에 필요한 데이터 부족

Stage 1/3은 모양만으로 완벽히 구분하기 어렵기 때문에 **과거의 가장 최근 확정 Stage 2/4 상태**를 사용해
사이클 문맥을 보존합니다. 미래 데이터는 사용하지 않습니다.

## 주요 출력

```text
results/<YYYYMMDD>/
├─ stage_screen.csv
└─ stage2_candidates.csv
```

`stage2_candidates.csv`는 현재 단계에서 **추세 조건만 통과한 후보**입니다.
향후 Market Regime, RS, Base, Breakout 조건이 추가되기 전에는 최종 매수 후보가 아닙니다.

## 실행

```bat
run_screen.bat
```

또는:

```bash
python main.py --date 20260904 --top-n 100
```

Universe Excel을 직접 지정하려면:

```bash
python main.py --date 20260904 --universe-xlsx "C:\path\to\KOSPI_Info.xlsx"
```

환경변수 `LIQUIDITY_UNIVERSE_XLSX`도 지원합니다.

## 테스트

```bash
python -m pytest tests -q
```
