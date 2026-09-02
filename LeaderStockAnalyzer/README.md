# LeaderStockAnalyzer

재료·뉴스·테마 정보를 사용하지 않고 **시장 가격/거래량/거래대금/차트 위치/시장 대비 강도**만으로 주도주를 랭킹하는 독립 Analyzer입니다.

## V1 핵심 철학

1. 거래대금이 실제로 집중되는가
2. 당일 상승 강도가 충분한가
3. 10일/20일/52일 고점 또는 전고점 돌파 위치인가
4. 장중 고가를 반복 갱신하는가 (분봉 데이터가 있을 때)
5. KOSPI/KOSDAQ 대비 상대강도가 높은가
6. 종목 선정(Leader Score)과 진입 위치(Timing Score)를 분리한다
7. 높은 점수라도 과열/윗꼬리/이격 과다이면 Chase Risk로 제어한다

## Leader Score

기본 가중치:

- Money Flow 30
- Price Strength 20
- Daily Position 20
- Intraday Strength 15
- Market Relative Strength 10
- MA Structure 5

분봉 데이터가 없으면 Intraday Strength를 0점 처리하지 않고 **해당 가중치를 제외한 뒤 사용 가능한 신호만 재정규화**합니다.

## Timing

분봉이 있으면 다음 상태를 구분합니다.

`DISCOVERED -> BREAKOUT -> PULLBACK_WAIT -> SUPPORT_TEST -> ENTRY_READY`

분봉이 없으면 일봉만으로 눌림/지지/턴을 추측하지 않고 `DAILY_BREAKOUT_PROXY`를 사용합니다.

## 분봉 CSV (선택)

pykrx는 분봉을 제공하지 않으므로 아래 경로에 1분봉 CSV가 존재할 때 자동 활성화됩니다.

```text
data/intraday/YYYYMMDD/005930.csv
```

필수 컬럼:

```text
timestamp,open,high,low,close,volume
```

`trading_value`는 선택이며 없으면 `close * volume`으로 계산합니다.

## 실행

```bat
run_screen.bat
```

또는:

```bash
python main.py --date 20260902 --top-n 100
```

결과:

```text
results/YYYYMMDD/leader_screen.csv
results/YYYYMMDD/confirmed_candidates.csv
```

Range:

```bat
run_range.bat
```

```bash
python main_range.py --date-range 20260101~20260831 --top-n 100
```

Range 결과에는 `D+1`, `D+5`, `D+20`, `D+60` 종가 기준 수익률이 추가됩니다.

## 상태

- `STRONG_CONFIRMED`: Leader 85+, Timing 75+, 시장 Leader Rank 5위 이내, Chase Risk < 60
- `CONFIRMED`: Leader 75+, Timing 70+, Chase Risk < 60
- `WATCH`: Leader 65+
- `REJECT`: 그 외

모든 임계값과 가중치는 `config/default.yaml`에서 변경할 수 있습니다.
