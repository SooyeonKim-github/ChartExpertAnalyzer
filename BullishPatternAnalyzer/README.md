# BullishPatternAnalyzer V1.1

국내 주식 일봉에서 강의 기반 상승 차트 패턴을 독립적으로 탐지하고 백테스트하는 Analyzer다.
기존 `KJBChartAnalyzer`, `SwingChartProbabilityAnalyzer`와 결과를 합치지 않는다.

## 패턴

1. Ascending Triangle
2. Symmetrical Triangle — 상방 돌파만 bullish confirmation
3. Bull Flag
4. Falling Wedge
5. W Pattern
6. Inverse Head & Shoulders

## V1.1 확인 계층

패턴 모양만으로 후보를 확정하지 않고 다음 확인 요소를 별도로 계산한다.

- 돌파 거래량: 기본적으로 20일 평균 거래량의 1.3배 이상
- 돌파 전 거래량 수축: 최근 5일 평균 / 최근 20일 평균
- Volume Oscillator: 5일 거래량 평균과 20일 평균 차이
- MFI(14) 및 MFI 상승 다이버전스
- 상승 모멘텀 장대양봉과 종가 고가권 마감
- 강세 핀바(긴 아래꼬리)
- 상승 장악형 / 장악형 확인봉
- 강세 인사이드바 돌파 + Mother bar보다 큰 돌파 거래량
- 모닝스타
- 적삼병
- 고점권 반복 윗꼬리 + 증가 거래량 경고
- 저항/고점권 좁은 몸통 + 대량거래 경고

가격만 저항을 돌파하고 거래량 필터를 통과하지 못한 경우 `ENTRY_READY`로 승격하지 않는다. 해당 표본은 WATCH/전체 탐지 데이터에는 남겨 가짜 돌파 성능을 비교할 수 있다.

## 기간 백테스트

```bash
python main_range.py --date-range 20260501~20260531 --top-n 100
```

출력:

```text
results/range_YYYYMMDD_YYYYMMDD/
  range_all_detections.csv
  events.csv
  performance_by_pattern.csv
  performance_by_pattern_all.csv
  performance_by_state.csv
  performance_by_volume.csv
  performance_by_market_regime.csv
  performance_by_condition.csv
  range_summary.md
```

- `range_all_detections.csv`: FORMING/WATCH/거래량 탈락/확정 상태를 모두 보존한다.
- `events.csv`: 거래량 필터를 통과한 actionable 이벤트만 저장하며 동일 종목·동일 패턴은 기본 10거래일 cooldown을 둔다.
- 진입 가격은 신호일 종가가 아니라 다음 거래일 시가(`NEXT_OPEN`)다.
- D+1/3/5/10/20/40/60 수익률과 MFE/MAE를 함께 저장한다.

## 초기값 주의

`1.3배`, 거래량 수축 `0.85`, 캔들 몸통/꼬리 임계값 등은 강의가 정한 고정 숫자가 아니라 V1.1 백테스트용 초기값이다. `config.py`에서 수정하고 `performance_by_volume.csv`, `performance_by_condition.csv` 결과로 보정하는 것을 전제로 한다.
