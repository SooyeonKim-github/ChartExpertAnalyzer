# DynamicChartAnalyzer

`DynamicChartAnalyzer`는 강의록의 핵심인 **RSI → MACD → 일목균형표** 확인 순서와 **1:2:7 분할 진입/청산**을 재현 가능한 Python 규칙으로 옮긴 차트 분석기입니다.

강의에서 정확한 수식이 공개된 규칙과, 사람이 차트를 보며 표현한 정성적 규칙을 구분합니다. 정성적 표현(다이버전스 피벗, 강한 캔들, 구름 리테스트, 두꺼운 구름 등)은 설정값으로 명시해 백테스트 가능하게 만들었으며, 원본 강의의 독점 공식을 임의로 주장하지 않습니다.

## 핵심 전략

### LONG 3단계 진입

| 단계 | 조건 | 비중 | 1,000만원 기준 |
|---|---|---:|---:|
| Stage 1 | RSI가 30 이하에 들어갔다가 다시 30 위로 복귀 | 10% | 1,000,000원 |
| Stage 2 | MACD 골든크로스, 기본적으로 0선 아래 + 히스토그램 개선 | +20% | 2,000,000원 |
| Stage 3 | 전환선 > 기준선, 가격 > 구름, 후행스팬 강세 + 리테스트/강한 캔들 확인 | +70% | 7,000,000원 |

총 10,000,000원을 한 번에 넣지 않고 **100만원 → 200만원 → 700만원** 순서로 확인 강도가 높아질수록 비중을 확대합니다.

### SHORT 3단계 진입

LONG의 대칭 구조입니다.

1. RSI가 70 이상 과매수 영역에 들어갔다가 다시 70 아래로 복귀: 10%
2. MACD 데드크로스 + 히스토그램 약화: +20%
3. 전환선 < 기준선, 가격 < 구름, 후행스팬 약세 + 구름 이탈 확인: +70%

## 1:2:7 청산

### LONG

1. MACD 데드크로스: 10% 청산
2. RSI 50 하향 이탈: 추가 20% 청산
3. 가격 구름대 하향 이탈: 나머지 70% 청산

### SHORT

1. MACD 골든크로스: 10% 청산
2. RSI 50 상향 돌파: 추가 20% 청산
3. 가격 구름대 상향 돌파: 나머지 70% 청산

**중요:** 위 10/20/70 추세 청산은 Stage 3까지 완전히 확인된 포지션에 적용합니다. Stage 1 또는 Stage 2만 들어간 미확정 포지션은 보호 손절 또는 신호 유효기간 만료로 전체 정리합니다.

## 강의록 기반 V2 보강 사항

초기 버전보다 다음 항목을 추가했습니다.

### 1. RSI 다이버전스

- 상승 다이버전스: 가격의 새 저점은 낮거나 비슷하지만 RSI 저점은 상승
- 하락 다이버전스: 가격의 새 고점은 높거나 비슷하지만 RSI 고점은 하락
- centered pivot을 그대로 과거 시점에 기록하지 않고, 우측 확인봉이 지난 뒤에만 신호를 활성화해 **look-ahead를 방지**합니다.
- 1:2:7 Stage 1의 필수조건으로 강제하지 않고 `confidence enhancer`로 기록합니다.

### 2. MACD 히스토그램 방향

Stage 2에서 단순 크로스만 보지 않고 다음 필드를 함께 계산합니다.

- `macd_hist_rising`
- `macd_hist_falling`
- `macd_hist_turn_positive`
- `macd_hist_turn_negative`

LONG Stage 2는 **0선 아래 골든크로스 + 히스토그램 개선**을 기본 확인으로 사용합니다.

### 3. 캔들 확인

강의의 "직전 음봉을 덮는 상승 장대양봉"을 기계화했습니다.

- `bullish_engulfing`
- `bearish_engulfing`
- `strong_bullish_candle`
- `strong_bearish_candle`
- `doji_risk`

강한 캔들은 ATR 대비 몸통 비율로 판정하며 기본값은 `0.55 ATR`입니다.

별도로 강의 초반 예시인

`다이버전스 → MACD → 강한 캔들`

조합을 `classic_long_trigger`, `classic_short_trigger`로 출력합니다. 이 신호는 1:2:7 상태머신과 별도로 확인할 수 있습니다.

### 4. 구름 돌파 / 리테스트 / 두께

- `cloud_breakout`, `cloud_breakdown`
- `cloud_retest_hold`, `cloud_retest_reject`
- `cloud_width`, `cloud_width_atr`, `thick_cloud`

구름을 한 번 뚫었다는 이유만으로 Stage 3을 확정하지 않고, 기본적으로 **구름 리테스트 지지/저항 확인 또는 전환선 교차 + 강한 캔들**을 요구합니다. 도지 위험 캔들은 Stage 3에서 제외합니다.

### 5. 후행스팬 비-룩어헤드 처리

현재 종가와 26봉 전 종가를 비교하여 현재 시점에서 이미 알 수 있는 데이터만으로 강세/약세를 확인합니다.

### 6. 신호 유효기간

강의의 3단계 신호는 하나의 연속된 반전 과정으로 해석합니다. 따라서 초기 RSI 신호가 나온 뒤 몇 달 후의 무관한 MACD 신호가 Stage 2가 되는 문제를 막았습니다.

기본값:

- Stage 1 → Stage 2: 최대 15봉
- Stage 2 → Stage 3: 최대 20봉

기한을 넘기면 현재 미확정 물량을 `STAGE2_CONFIRMATION_TIMEOUT` 또는 `STAGE3_CONFIRMATION_TIMEOUT`으로 정리합니다. 이 기간은 강의에 직접 제시된 숫자가 아니라 백테스트를 위한 명시적 구현값이므로 `StrategyConfig`에서 조정할 수 있습니다.

### 7. 직전 스윙 손절

강의의 "직전 저점/고점에 손절"을 다음처럼 구현했습니다.

- LONG: 진입 전 최근 N봉 저점
- SHORT: 진입 전 최근 N봉 고점
- 기본 N = 10
- 현재 봉을 손절 계산에 넣지 않고 `shift(1)` 처리
- 일봉 갭 하락/상승 시에는 시가를 고려한 보수적인 체결가격 사용

손절가는 `events.csv`에 기록됩니다.

### 8. 참고 손익비

강의 예시의 손익비를 참고 목표가로 계산합니다.

- LONG reference RR: 1:1
- SHORT reference RR: 1:2

다만 메인 전략의 실제 청산은 MACD → RSI 50 → 구름대의 1:2:7 추세 청산이므로, 이 목표가는 **참고값**이며 자동 목표가 청산 조건으로 사용하지 않습니다.

### 9. 선택 가능한 2% Risk Rule

기본 모드는 사용자의 요구대로 정확히 다음 금액을 사용합니다.

```text
Total   = 10,000,000원
Stage 1 =  1,000,000원
Stage 2 =  2,000,000원
Stage 3 =  7,000,000원
```

`--risk-cap`을 켜면 강의 후반의 계좌 2% 위험 제한을 적용합니다.

```text
최대 포지션 금액
= 총 계좌 × 2% / 손절거리(% 중 소수표현)
```

예를 들어 1,000만원 계좌에서 손절거리가 4%라면 최대 포지션은 500만원이고 이를 다시 1:2:7로 나눕니다.

```text
Stage 1 =  500,000원
Stage 2 = 1,000,000원
Stage 3 = 3,500,000원
```

## Dynamic RSI에 대한 처리

강의 후반의 Dynamic RSI는 프라이빗 지표이며 정확한 계산식이 공개되지 않습니다.

`experimental_dynamic_rsi()`는 다음 아이디어만 투명하게 근사합니다.

- 최근 RSI에 더 높은 가중치
- 이동 중심선
- 변동성에 따라 움직이는 상/하단 밴드

이 모듈은 **실험용**이며 기본 진입 로직에는 사용하지 않습니다. `--dynamic-rsi`를 켜면 분석 CSV에만 추가됩니다.

## 폴더 구조

```text
DynamicChartAnalyzer/
├─ main.py
├─ run_screen.bat
├─ requirements.txt
├─ README.md
├─ dynamic_chart_analyzer/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ indicators.py
│  ├─ signals.py
│  ├─ position_manager.py
│  ├─ analyzer.py
│  └─ providers/
│     ├─ __init__.py
│     ├─ csv_provider.py
│     └─ pykrx_provider.py
├─ tests/
│  ├─ test_position_manager.py
│  └─ test_signals.py
└─ results/
   └─ .gitkeep
```

## 설치

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 실행

### 1. 1,000만원 1:2:7 배분만 확인

```bash
python main.py --show-plan
```

### 2. CSV 분석

입력 컬럼은 `date, open, high, low, close, volume` 또는 한글 OHLCV 컬럼을 지원합니다.

```bash
python main.py --csv sample.csv --capital 10000000
```

### 3. KRX 종목 분석

```bash
python main.py --ticker 005930 --start 20250101 --end 20260831 --capital 10000000
```

### 4. 2% 위험 제한 사용

```bash
python main.py --ticker 005930 --start 20250101 --end 20260831 --capital 10000000 --risk-cap
```

### 5. 실험용 Dynamic RSI 출력

```bash
python main.py --ticker 005930 --start 20250101 --end 20260831 --dynamic-rsi
```

## 출력 파일

- `results/<ticker>_analysis.csv`
  - RSI / MACD / Ichimoku / ATR
  - 다이버전스 / 캔들 / 구름 리테스트
  - 각 Stage 신호
  - 실제 상태머신의 현재 Stage
  - 다음 예정 투입액
  - 보호 손절 / 참고 목표가
  - 미실현손익

- `results/<ticker>_events.csv`
  - 각 Stage 실제 진입 시점
  - 투입 금액 / 수량 / 가중평균 진입가
  - 보호 손절가
  - 단계별 청산
  - 실현손익
  - Timeout/Stop 정리 사유

## 상태 값

분석 CSV의 `position_status`는 다음 중 하나입니다.

```text
FLAT
LONG_EARLY
LONG_CONFIRMING
LONG_CONFIRMED
SHORT_EARLY
SHORT_CONFIRMING
SHORT_CONFIRMED
```

따라서 다른 Analyzer 또는 Agent가 결과를 읽을 때 단순 BUY/SELL이 아니라 **현재 1:2:7 중 어느 확인 단계까지 왔는지** 판단할 수 있습니다.

## 테스트

```bash
python -m pytest -q
```

현재 테스트는 다음을 검증합니다.

- 1,000만원 = 100만원 / 200만원 / 700만원
- 선택적 2% 위험 제한
- Stage 순차 진행 강제
- 1:2:7 청산 시 PnL 계산
- 보강된 다이버전스/MACD/구름/캔들 컬럼 생성

## 구현 원칙

1. 미래 데이터를 사용해 과거 신호를 좋게 보이게 만들지 않는다.
2. 강의에서 정확히 말하지 않은 숫자는 설정값으로 노출한다.
3. RSI/MACD/일목균형표의 역할을 합쳐 하나의 점수로 뭉개지 않고 Stage별 근거를 유지한다.
4. 기본 자금배분은 1:2:7을 그대로 지킨다.
5. Dynamic RSI의 독점 공식을 재현했다고 주장하지 않는다.
