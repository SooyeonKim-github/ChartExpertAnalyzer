# Bullish Pattern Lecture Mapping

이 문서는 강의에서 반복적으로 강조된 패턴·거래량·캔들 원칙이 코드 어디에 반영됐는지 추적하기 위한 문서다. 강의에 숫자로 제시되지 않은 임계값은 `config.py`의 초기값이며 반드시 백테스트로 보정한다.

## 기존 패턴 원칙

- 패턴 완성 전 예측성 진입을 피한다.
- 저항/넥라인/추세선의 상향 돌파를 확인한다.
- 돌파 시 거래량 증가를 신뢰도 강화 요소로 본다.
- 돌파를 놓쳤다면 리테스트를 별도로 평가한다.

### W Pattern

- 두 번째 저점이 첫 번째 저점보다 높을수록 우수.
- 두 번째 하락 거래량이 첫 번째 하락보다 감소하는지 확인.
- 두 번째 저점과 20일선 이격, 두 번째 하락의 완만함, 첫 반등 고점(넥라인)을 함께 평가.
- 구현: `patterns/reversal.py::WPatternDetector`.

### Bull Flag / Triangle / Falling Wedge

- 조정/수렴 중 거래량 감소와 저항선 돌파 시 거래량 재증가를 공통 확인 요소로 사용.
- 구현: 각 pattern detector + `core/analysis.py::volume_quality`.

## V1.1 거래량 고도화

강의의 핵심은 가격 움직임의 신뢰도를 거래량으로 확인하고, 특히 돌파 순간의 거래량으로 가짜 돌파를 걸러내는 것이다.

구현:

- `vol_ma5`, `vol_ma20`
- Volume Oscillator `(vol_ma5 - vol_ma20) / vol_ma20`
- 돌파 당일 거래량 / 20일 평균 거래량
- 돌파 전 최근 5일 거래량 수축 여부
- 가격 상승 + 거래량 하락의 bearish volume divergence 경고
- MFI(14) 및 MFI bullish divergence
- 구현 파일: `core/indicators.py`, `core/analysis.py`, `core/scorer.py`.

기본 actionable 거래량 필터는 돌파 당일 거래량이 20일 평균의 1.3배 이상인 경우다. 이 수치는 강의의 고정 기준이 아니라 초기 백테스트 값이다.

## V1.1 캔들 고도화

강의에서 캔들의 몸통은 방향성/모멘텀, 꼬리는 지지·저항에서의 공방 흔적으로 설명한다. 이를 `core/candle_analysis.py`에 공통 confirmation layer로 구현했다.

상승 확인:

- 몸통이 크고 종가가 고가권에 위치한 bullish momentum candle
- 긴 아래꼬리 강세 핀바
- 상승 장악형 및 다음 봉 확인
- 강세 인사이드바의 Mother bar 고점 돌파 + 더 큰 거래량
- 모닝스타
- 적삼병

경고/차단:

- 고점권에서 긴 윗꼬리가 연속되고 거래량이 증가하는 분배형 신호
- 저항/고점권에서 좁은 몸통인데 대량 거래량이 발생하는 흡수/매도압력 경고

캔들 패턴은 기존 6개 가격 패턴을 대체하지 않고 `Selection/Timing` 확인 요소로만 사용한다.

## 백테스트 개선

- 모든 탐지 상태를 `range_all_detections.csv`에 보존한다.
- 거래량 필터 통과 이벤트만 `events.csv`에 저장한다.
- 동일 종목·동일 패턴의 연속 이벤트는 기본 10거래일 cooldown.
- 진입은 다음 거래일 시가 기준.
- D+1/3/5/10/20/40/60 return + MFE/MAE 기록.
- 패턴/상태/거래량구간/시장국면/확인조건별 성능을 각각 출력한다.
