# SwingChartProbabilityAnalyzer

유튜브 영상 **「전형적인 스윙매매 차트매매의 정석입니다」**의 설명만 정량화한 스윙 차트 선별 프로젝트입니다.

## 1. 영상 규칙 → 코드 규칙

이 프로젝트는 RSI, MACD, DMI, 볼린저밴드, 시장지수, 외국인/기관 수급, 재무지표를 **신호에 사용하지 않습니다.**
`KOSPI_Info.xlsx`는 오직 종목코드/종목명 유니버스를 정하는 데 사용합니다.

1. **중기 상승추세**: 최근 확정 스윙고점 2개가 Higher High이고 최근 확정 스윙저점 2개가 Higher Low.
2. **단기 조정**: 최근 고점에서 일정폭 내려왔지만 최근 스윙저점을 훼손하지 않음.
3. **상승 평행채널**: 확정 고점 2개를 잇는 상단선을 만들고, 동일 기울기의 선을 확정 저점으로 평행이동. 과거 가격이 채널 안에 충분히 머문 조합만 인정.
4. **싼 구간**: 채널 하단에 최근 접촉했고 현재도 채널 중심 아래/근처에 위치.
5. **바닥 확인**: 하단에서 두 저점이 비슷하거나 두 번째 저점이 높아지는 쌍바닥. 넥라인 돌파 시 확인 신호 강화.
6. **이평선**: 영상의 '이평선 밀집 → 이평선 재돌파 → 5일선 지지'를 구현. 기본 기간 5/20/60은 정성 표현을 코드화하기 위한 설정값이며 변경 가능.
7. **바닥 거래량**: 채널 하단에서 직전 20일 평균 대비 거래량 급증 + 양봉을 '기준봉'으로 지정.
8. **기준봉 지지/돌파**: 이후 조정이 기준봉 저가를 지키고 다시 상승하거나 기준봉 고가를 돌파하면 확인 매수 신호.
9. **목표**: 채널 중심 → 최근 전고점 → 채널 상단.
10. **손절**: 상승채널 하단 또는 최근 스윙저점을 3% 이상 훼손하면 실패 처리. 영상에서 제시한 3~5% 예시 중 3%를 기본값으로 사용.

## 2. '상승 가능 확률'의 의미

점수를 임의로 확률로 바꾸지 않습니다. `calibrate`를 먼저 실행하면 과거 날짜를 하루씩 되감아 **당시 알 수 있던 데이터만**으로 신호를 재생합니다. 신호 발생 후 20거래일 안에:

- 채널 중심을 손절보다 먼저 도달했는가
- 전고점을 손절보다 먼저 도달했는가
- 채널 상단을 손절보다 먼저 도달했는가

를 기록합니다. 현재 종목과 **영상 패턴 서명(채널 위치·쌍바닥 확인·이평 밀집/재돌파·바닥 거래량·기준봉 지지/돌파)**이 같은 과거 표본을 우선 사용하고, 표본이 부족할 때만 `Status + Score Band`로 완화합니다. 실제 성공률은 Beta smoothing하여 확률로 표시합니다. 표본이 너무 적으면 확률은 빈 값으로 둡니다.

## 3. 설치

```bash
cd SwingChartProbabilityAnalyzer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 4. 과거 성공확률 만들기

```bash
python main.py calibrate --start 2024-01-01 --end 2026-06-30 --top-n 200 --step 3
```

- `--top-n 200`: KOSPI_Info.xlsx에서 시총순 200개만 계산. 0은 전체.
- `--step 3`: 3거래일 간격으로 과거 신호를 재생해 계산량을 줄임. 같은 종목의 동일 상승구간이 중복 집계되지 않도록 신호 발생 후 기본 10거래일 cooldown을 둡니다.
- 결과: `results/calibration_events.csv`

## 5. 현재 종목 스캔

```bash
python main.py scan --date 2026-08-21 --top-n 0 --charts 30
```

주말 날짜를 넣어도 pykrx가 반환한 마지막 거래일을 `Actual_Date`로 기록합니다.

결과:

```text
results/20260821/
  scan_results.csv
  candidates.csv
  swing_candidates.xlsx
  charts/
    005930_삼성전자.png
    ...
```

## 6. 개별 종목 상세 분석

```bash
python main.py explain --ticker 171090 --date 2026-08-21
```

## 7. 점수(100점)

- 중기 HH+HL: 20
- 상승추세 안 단기조정 + 전저점 유지: 10
- 상승 평행채널 품질: 10
- 최근 채널 하단 접촉: 10
- 현재 채널 하단권: 5
- 쌍바닥/Higher-Low: 5, 넥라인 돌파: +5
- 이평선 밀집: 8, 재돌파: +8
- 바닥 거래량 급증 양봉: 10
- 기준봉 저가 지지: 4
- 기준봉 고가 돌파: 5 (지지 후 단순 재상승은 3)
- 이평 재돌파 후 5일선 지지: 2

**CONFIRMED**는 점수만 높다고 되지 않습니다. 중기상승 구조, 전저점 유지, 채널 미이탈이 필수이며, 최근 하단 접촉과 실제 반전 확인도 필요합니다.

## 8. 미래참조 방지

스윙 고점/저점은 오른쪽 `pivot_window`개의 봉이 지난 뒤에만 확정합니다. `calibrate` 시 각 과거 날짜마다 DataFrame을 그 날짜까지만 잘라 분석하기 때문에 이후 가격으로 당시 추세선/쌍바닥을 미리 확정하지 않습니다.

## 9. 중요

이 프로젝트의 `Prob_*`는 투자수익을 보장하는 예측확률이 아니라 **정의한 영상 패턴이 과거 동일 조건에서 목표를 손절보다 먼저 도달한 경험적 비율**입니다. 종목/시장 환경이 바뀌면 성공률도 바뀔 수 있으므로 정기적으로 calibration을 다시 만드는 방식이 적합합니다.

---

## 기간 분석 + 향후 20거래일 실제 수익률

Windows에서는 `run_swing_range.bat`을 더블클릭하거나 아래처럼 실행할 수 있습니다.

```bat
run_swing_range.bat 20260701~20260724 100 market_cap
```

인자:

1. `DATE_RANGE`: `YYYYMMDD~YYYYMMDD`
2. `TOP_N`: 분석 종목 수. `0`이면 `KOSPI_Info.xlsx`의 일반주 전체
3. `SORT_BY`: `market_cap`, `trading_value`, `volume`

실제 실행 명령은 다음과 같습니다.

```bash
python main_range.py --date-range 20260701~20260724 --top-n 100 --sort-by market_cap --forward-bars 20
```

기간 내 각 종목의 **실제 거래일마다** 그 날짜까지의 데이터만 잘라 영상 규칙 기반 신호를 다시 계산합니다. 미래 20거래일 데이터는 Analyzer가 신호를 모두 만든 뒤 사후 성과평가에만 사용하므로 미래참조(look-ahead)가 발생하지 않도록 분리되어 있습니다.

결과 폴더:

```text
results/range_20260701_20260724/
├─ swing_range_backtest.xlsx
├─ range_candidates.csv
└─ range_all_results.csv
```

`range_candidates`에는 `CONFIRMED`, `WATCH`만 저장되며 다음 사후 성과가 함께 기록됩니다.

- `D+1_Close_Return_Pct` ~ `D+20_Close_Return_Pct`: 신호일 종가 대비 다음 N번째 거래봉 종가 수익률
- `D+20_Close_Return_Pct`: 정확히 20번째 거래봉 종가 수익률
- `MFE_20D_Pct`: 20거래일 동안 신호일 종가 대비 가장 높았던 고가 수익률
- `MAE_20D_Pct`: 20거래일 동안 신호일 종가 대비 가장 낮았던 저가 수익률
- `Max_Close_Return_20D_Pct`, `Min_Close_Return_20D_Pct`: 20거래일 내 종가 기준 최고/최저 수익률
- `Hit_Mid_Before_Stop`: 영상의 채널 중심 목표가를 손절보다 먼저 도달했는지
- `Hit_PriorHigh_Before_Stop`: 전고점을 손절보다 먼저 도달했는지
- `Hit_Upper_Before_Stop`: 채널 상단을 손절보다 먼저 도달했는지
- `Stop_Hit`: 20거래일 내 영상 규칙의 추세/저점 손절선 도달 여부
- `Forward_Complete_20D`: 실제 미래 20거래봉이 모두 존재하면 1, 아직 부족하면 0

Excel에는 `performance_by_date`, `performance_by_status`, `performance_by_score` 시트도 추가되어 기간 전체의 D+20 승률, 평균/중앙 수익률, 평균 MFE/MAE를 바로 비교할 수 있습니다.

> 주의: 기간 종료일 이후 20거래일이 아직 지나지 않았다면 해당 행의 D+20 수익률은 비어 있습니다. 미래 데이터가 실제로 쌓인 뒤 같은 기간을 다시 실행하면 자동으로 채워집니다.
