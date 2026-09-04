# LeaderStockAnalyzer

재료·뉴스·테마 정보를 사용하지 않고 **시장 가격/거래량/거래대금/차트 위치/시장 대비 강도**만으로 주도주를 랭킹하는 독립 Analyzer입니다.

## 핵심 철학

1. 거래대금이 실제로 집중되는가
2. 당일 상승 강도가 충분한가
3. 10일/20일/52일 고점 또는 전고점 돌파 위치인가
4. 돌파가 발생했다면 그 돌파 자체의 품질이 좋은가
5. 장중 고가를 반복 갱신하는가 (분봉 데이터가 있을 때)
6. KOSPI/KOSDAQ 대비 상대강도가 높은가
7. 종목 선정(Leader Score)과 진입 위치(Timing Score)를 분리한다
8. 높은 점수라도 과열/윗꼬리/이격 과다이면 Chase Risk로 제어한다
9. 강한 업종 안에서 실제 대장인지 Sector Context로 확인한다
10. 오늘만 강한 종목과 며칠째 시장 중심인 종목을 Leader Persistence로 구분한다

## Leader Score

기본 가중치:

- Money Flow 30
- Price Strength 20
- Daily Position 20
- Intraday Strength 15
- Market Relative Strength 10
- MA Structure 5

분봉 데이터가 없으면 Intraday Strength를 0점 처리하지 않고 **해당 가중치를 제외한 뒤 사용 가능한 신호만 재정규화**합니다.

Sector Context, Persistence, Breakout Quality는 기존 100점 Leader Score에 억지로 합산하지 않고 독립 Context로 유지합니다. 따라서 Range 백테스트에서 각 로직의 효과를 따로 검증할 수 있습니다.

## Breakout Quality

돌파 여부와 돌파 품질을 분리합니다. Primary breakout 우선순위는 다음과 같습니다.

`PREVIOUS_HIGH_BREAK -> 52D_HIGH_BREAK -> 20D_HIGH_BREAK -> 10D_HIGH_BREAK`

실제 돌파가 있을 때 다음 항목을 0~100점으로 평가합니다.

- `breakout_distance_pct`: 돌파선 대비 종가 돌파폭
- `close_location_value`: 당일 Range 내 종가 위치
- `upper_wick_ratio`: 윗꼬리 비율
- `volume_ratio_20`: 최근 20일 대비 거래량 확장
- `turnover_ratio_20`: 최근 20일 대비 거래대금 확장
- `breakout_hold_pct`: 종가 기준 돌파선 유지 정도
- `gap_pct`: 전일 종가 대비 시가 갭
- `pre_breakout_distance_pct`: 돌파 전날 고점 접근 정도
- `volatility_contraction_ratio`: 돌파 전 단기 변동성 수축 정도

등급:

- `CLEAN_BREAKOUT`: 85+
- `VALID_BREAKOUT`: 70+
- `WEAK_BREAKOUT`: 50+
- `FAILED_BREAKOUT`: 50 미만 또는 강제 실패 조건
- `NO_BREAKOUT`: 당일 실제 돌파가 없음

강제 실패/위험 규칙도 별도로 둡니다.

- 장중 돌파 후 종가가 다시 돌파선 아래이면 `false_breakout_flag=true` + `FAILED_BREAKOUT`
- 과도한 갭 이후 종가 위치가 약하면 `FAILED_BREAKOUT`
- 매우 긴 윗꼬리는 `CLEAN/VALID`를 `WEAK`로 하향
- 과도한 거래대금 폭발 + 긴 윗꼬리, 과도한 갭 + 약한 종가, 돌파폭 과다는 `breakout_exhaustion_risk=true`

Breakout Quality와 Chase Risk의 목적은 다릅니다.

- Breakout Quality: **돌파 자체가 건강한가**
- Chase Risk: **지금 가격에서 따라붙는 것이 위험한가**

실제 돌파가 있는 종목은 기본 설정에서 `STRONG_CONFIRMED`에 Quality 70+, `CONFIRMED`에 Quality 55+를 요구합니다. `FAILED_BREAKOUT`은 Leader/Timing이 높더라도 `WATCH`로 강등합니다. 돌파가 없는 종목은 `NO_BREAKOUT`으로 두고 품질 점수 때문에 자동 탈락시키지 않습니다.

## Sector Context

종목의 업종은 분석일 기준 KRX 업종 분류를 사용하고 `cache/sectors/YYYYMMDD.csv`에 캐시합니다.

분석 대상 거래대금 TOP N 종목의 실제 일봉 이력으로 다음 값을 계산합니다.

- `sector_ret_5d`, `sector_ret_20d`
- `sector_rs_5d`, `sector_rs_20d`: KOSPI/KOSDAQ 대비 업종 상대강도
- `sector_breadth`: 업종 내 상승 종목 비율
- `sector_turnover_ratio`: 최근 20일 대비 업종 거래대금 강도
- `sector_strength_score`, `sector_market_rank`
- `stock_vs_sector_rs_5d`, `stock_vs_sector_rs_20d`
- `sector_leader_score`, `sector_leader_rank`

업종 구성 종목이 너무 적으면 `sector_context_reliable=false`로 두어 최종 판정에 강하게 사용하지 않습니다.

## Leader Persistence

최근 며칠 동안 거래대금 상위권이 지속되었는지를 분석 대상 TOP N 종목의 과거 거래대금으로 재구성합니다. 과거 Analyzer 결과 파일이 없어도 Range에서 동작합니다.

기본 저장값:

- `leader_persistence_score`
- `leader_persistence_level`: `HIGH / MEDIUM / LOW`
- `turnover_rank_avg_5d`
- `turnover_top20_days_5d`
- `turnover_top50_days_10d`
- `strong_return_days_5d`

`leader_type`은 다음과 같이 분리합니다.

- `PERSISTENT_LEADER`: 최근에도 지속적으로 거래대금 상위권
- `EMERGING_LEADER`: 최근 주도 이력은 적지만 오늘 Leader Score/Rank가 강하게 등장
- `NORMAL`: 그 외

Persistence가 낮다는 이유만으로 신규 주도주를 자동 탈락시키지 않습니다.

## 최종 상태 판정

기본 Leader/Timing/Chase 조건에 Breakout Quality와 Context를 추가합니다.

- `STRONG_CONFIRMED`: Strong 조건 + 실제 돌파일 경우 Quality 기준 통과 + Context가 있으면 강한 업종/지속 주도/신규 주도 중 하나로 확인
- `CONFIRMED`: Confirmed 조건 + 실제 돌파일 경우 최소 Quality 기준 통과
- `WATCH`: Timing 부족, Chase Risk 과다, Failed/저품질 돌파, 또는 약한 업종 + 낮은 Persistence 조합
- `REJECT`: 그 외

Context 데이터가 없는 경우에는 데이터 소스 장애 때문에 후보가 일괄 탈락하지 않도록 기존 판정 기준을 유지합니다.

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

Range 결과에는 Breakout Quality/Sector/Persistence 컬럼과 함께 `D+1`, `D+5`, `D+20`, `D+60` 종가 기준 수익률이 저장됩니다.

## 설정

모든 주요 가중치와 임계값은 `config/default.yaml`에서 변경할 수 있습니다.

```text
weights
thresholds
breakout_quality
sector_context
persistence
```

## 테스트

기존 Leader/Timing/Sector/Persistence 테스트에 Breakout Quality 합성 테스트를 포함합니다.

```bash
python -m pytest -q
```
