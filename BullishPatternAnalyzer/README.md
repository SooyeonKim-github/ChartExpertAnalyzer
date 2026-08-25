# BullishPatternAnalyzer V1

국내 주식 일봉에서 강의 기반 상승 차트 패턴을 독립적으로 탐지하고 백테스트하는 Analyzer다.
기존 `KJBChartAnalyzer`, `SwingChartProbabilityAnalyzer`와 코드/실행 결과를 합치지 않는다.

## V1 패턴

1. Ascending Triangle
2. Symmetrical Triangle — 상방 돌파된 경우만 bullish confirmation
3. Bull Flag
4. Falling Wedge
5. W Pattern
6. Inverse Head & Shoulders

## 공통 분석

- Swing high / swing low 기반 구조 탐지
- Breakout confirmation
- Breakout volume
- RSI 및 bullish divergence
- 5/20/60일 이동평균
- Retest
- Chase risk
- Entry-to-stop risk
- KOSPI/KOSDAQ market context

## 설치

```bash
cd BullishPatternAnalyzer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 일별 스캔

```bash
python main.py --date 20260825 --top-n 100
```

Windows에서는 `run_screen.bat`을 사용할 수 있다.

출력:

```text
results/YYYYMMDD/
  bullish_pattern_all.csv
  bullish_pattern_candidates.csv
  bullish_pattern_watchlist.csv
  summary.md
```

## 기간 백테스트

```bash
python main_range.py --date-range 20260501~20260531 --top-n 100
```

또는 `run_swing_range.bat`.

출력:

```text
results/range_YYYYMMDD_YYYYMMDD/
  events.csv
  performance_by_pattern.csv
  range_summary.md
```

Forward return은 D+1, D+3, D+5, D+10, D+20, D+40, D+60 거래일 기준으로 기록한다.

## 상태

- `FORMING`: 구조 형성 중
- `WATCH`: 구조는 유효하나 핵심 돌파 전
- `BREAKOUT_CONFIRMED`: 종가 기준 돌파 확인
- `RETEST`: 돌파 후 레벨 재확인 및 지지
- `ENTRY_READY`: 점수/리스크/시장상황까지 통과

## 점수

V1 점수는 초기 휴리스틱이며 강의에서 숫자로 제시한 값이 아니다.
모든 허용오차와 임계값은 `config.py`에서 수정할 수 있고, 기간 백테스트 결과로 보정하는 것을 전제로 한다.

## 유의사항

- `pykrx` 데이터 제공 상태에 따라 휴장일/일시적 API 오류가 발생할 수 있다.
- 패턴 탐지는 투자 권유가 아니라 정량화된 후보 탐색 도구다.
- V1은 일봉 중심이다. 피벗 포인트 기반 분봉 진입은 의도적으로 제외했다.
