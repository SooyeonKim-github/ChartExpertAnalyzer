# MAChartAnalyzer

사용자가 제공한 이동평균 매매 강의 내용을 기반으로 만든 **독립 BUY 판단 Analyzer**입니다.

기존 `KJBChartAnalyzer`, `SwingChartProbabilityAnalyzer`의 점수와 섞지 않고 별도의 신호를 생성합니다.

## 전략 구조

`Direction -> Timing -> Confirmation -> Sideways Filter -> Risk`

- 장기 방향: 200MA 위치 + 기울기
- 단기 타점: 단기 MA(기본 20) 눌림/재돌파
- Squeeze: 단기/장기 MA 간격 압축 후 추세 방향 탈출
- 돌파 확정: 장대 양봉 / MA와 캔들 완전 분리 / 직전 고점 몸통 돌파
- 횡보 회피: 짧은 구간 내 가격/이평 교차 반복
- 박스 재개: 횡보 박스 상단 강한 돌파
- 추격 방지: 단기 MA 대비 이격 과다
- 위험 신호: 장기 MA의 명확한 하향 훼손

상세한 강의 규칙과 코드 매핑은 `RULE_MAPPING.md` 참고.

## 중요

강의 자동자막은 단기 이동평균 값을 `20`, `22` 등으로 혼재하여 기록합니다.
V1은 단기 MA를 20으로 정규화했지만 `config.py`에서 변경 가능합니다.

또한 강의에 숫자로 제시되지 않은 Squeeze 간격, 장대봉 배수, 횡보 교차 횟수 등은
결정론적 백테스트를 위한 구현 파라미터입니다. 강의의 원문 숫자라고 간주하면 안 됩니다.

강의 후반의 '세력 지표'는 계산식이 공개되지 않아 구현하지 않았습니다.

## 설치

```bash
pip install -r requirements.txt
```

기본 Universe Excel은 저장소에 이미 있는
`../SwingChartProbabilityAnalyzer/KOSPI_Info.xlsx`를 사용합니다.
신호 로직은 Swing Analyzer와 공유하지 않습니다.

## 일일 스크리닝

```bash
python main.py scan --top-n 100
```

전체 Universe:

```bash
python main.py scan --top-n 0
```

특정 종목 설명:

```bash
python main.py explain --ticker 005930 --date 2026-08-28
```

Windows:

```bat
run_screen.bat 100
```

결과:

```text
results/YYYYMMDD/
  scan_results.csv
  candidates.csv
  ma_candidates.xlsx
```

## 기간 백테스트

```bash
python main_range.py \
  --date-range 20260101~20260821 \
  --top-n 100 \
  --sort-by market_cap \
  --forward-bars 60
```

Windows:

```bat
run_ma_range.bat 20260101~20260821 100 market_cap
```

결과:

```text
results/range_YYYYMMDD_YYYYMMDD/
  range_all_results.csv
  range_candidates.csv
  ma_range_backtest.xlsx
```

## 주요 출력 필드

- `Status`: CONFIRMED / WATCH / REJECTED
- `Score`: 방향 + 구조 + 확인 + 위험을 합친 점수
- `Timing_Score`: 현재 진입 타점의 강도
- `Primary_Signal`
- `Long_MA_Slope_Pct`, `Short_MA_Slope_Pct`
- `Squeeze_Compressed`, `Squeeze_Breakout`
- `Pullback_Reclaim`
- `Prior_High_Breakout`
- `Long_Bull_Body`
- `Detached_Above_MA`
- `Cross_Count`, `Sideways`
- `Box_Breakout`, `Box_Retest_Hold`
- `MA20_Distance_Pct`, `Chase_Risk`
- `Long_MA_Breakdown`
- `Stop_Entry_Candle_Low`, `Stop_Short_MA`

## V1 목적

첫 버전에서는 강의 내용의 구조를 최대한 누락 없이 코드화하고,
숫자로 공개되지 않은 임계값은 전부 `config.py`로 분리했습니다.

따라서 다음 단계는 기간 백테스트 결과를 보고
`CONFIRMED`의 D+5 / D+10 / D+20 / D+60 성능과 실패 원인을 기준으로
각 구현 임계값을 조정하는 것입니다.
