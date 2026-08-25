# Bullish Pattern Lecture Mapping

이 문서는 V1 구현이 강의의 어떤 원칙을 코드로 옮겼는지 추적하기 위한 문서다.
강의에 없던 수치형 임계값은 `config.py`의 초기값이며 백테스트로 보정해야 한다.

## 공통 원칙

- 패턴 완성 전 예측성 진입을 피한다.
- 저항/넥라인/추세선의 상향 돌파를 확인한다.
- 돌파 시 거래량 증가를 신뢰도 강화 요소로 본다.
- 돌파를 놓쳤다면 리테스트를 별도로 평가한다.

## Ascending Triangle

- 상단 저항은 거의 수평.
- 저점은 상승.
- 상단 저항 돌파를 확인.
- 구현: `patterns/triangles.py::AscendingTriangleDetector`.

## Symmetrical Triangle

- 고점 하락, 저점 상승으로 수렴.
- 방향은 사전에 확정하지 않으며 상방 돌파 시에만 상승 후보.
- 구현: `patterns/triangles.py::SymmetricalTriangleDetector`.

## Falling Wedge

- 고점과 저점은 하락하지만 폭이 수렴.
- 상단 추세선 돌파를 반전 확인으로 사용.
- 상승 다이버전스를 신뢰도 가산 요소로 사용.
- 구현: `patterns/reversal.py::FallingWedgeDetector`.

## Bull Flag

- 선행 급등(pole) 후 얕은 조정(flag).
- 조정 중 거래량 감소, 상단 돌파 시 거래량 재증가를 선호.
- 구현: `patterns/bull_flag.py::BullFlagDetector`.

## W Pattern

- 첫 번째 바닥보다 두 번째 바닥이 높을수록 우수.
- 두 번째 하락 거래량이 첫 번째 하락보다 감소하는지 확인.
- 두 번째 저점과 20일 이동평균선 이격이 작은지 확인.
- 두 번째 하락이 첫 번째 하락보다 완만한지 가산.
- 첫 반등 고점을 넥라인/1차 저항으로 사용.
- 두 번째 저점이 20일선 위면 5일선 회복, 아래면 20일선 회복을 WATCH 타이밍 정보로 사용.
- 최종 확인은 넥라인 돌파.
- 구현: `patterns/reversal.py::WPatternDetector`.

## Inverse Head & Shoulders

- 가운데 저점(head)이 양 어깨보다 낮음.
- 양 어깨 가격의 대칭성 확인.
- 넥라인 상향 돌파 확인.
- 구현: `patterns/reversal.py::InverseHeadShouldersDetector`.

## Market context

W 패턴 강의에서 지수가 우선이며 폭락장에서는 패턴 활용도가 낮다고 강조한다.
V1은 KOSPI/KOSDAQ 지수의 20/60일선 및 최근 drawdown으로 `BULLISH/NEUTRAL/WEAK/CRASH`를 분류한다.
`CRASH`에서는 `ENTRY_READY` 승격을 막는다.

## Pivot Point 강의

피벗 포인트 강의는 분봉 기반 데이트레이딩/스캘핑 성격이 강하므로 V1 일봉 패턴 탐지에는 포함하지 않았다.
향후 `IntradayEntryAnalyzer`를 별도 추가할 경우 피벗 기준선, R1/R2, S1/S2를 진입 타이밍에 활용할 수 있다.
