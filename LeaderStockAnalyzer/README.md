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
11. 미래 성과 평가는 same-day 판정 로직과 완전히 분리해 look-ahead를 방지한다

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

- `breakout_distance_pct`
- `close_location_value`
- `upper_wick_ratio`
- `volume_ratio_20`
- `turnover_ratio_20`
- `breakout_hold_pct`
- `gap_pct`
- `pre_breakout_distance_pct`
- `volatility_contraction_ratio`

등급:

- `CLEAN_BREAKOUT`: 85+
- `VALID_BREAKOUT`: 70+
- `WEAK_BREAKOUT`: 50+
- `FAILED_BREAKOUT`: 50 미만 또는 강제 실패 조건
- `NO_BREAKOUT`: 당일 실제 돌파가 없음

Breakout Quality와 Chase Risk의 목적은 다릅니다.

- Breakout Quality: **돌파 자체가 건강한가**
- Chase Risk: **지금 가격에서 따라붙는 것이 위험한가**

실제 돌파가 있는 종목은 기본 설정에서 `STRONG_CONFIRMED`에 Quality 70+, `CONFIRMED`에 Quality 55+를 요구합니다. `FAILED_BREAKOUT`은 Leader/Timing이 높더라도 `WATCH`로 강등합니다.

## Sector Context

종목의 업종은 분석일 기준 KRX 업종 분류를 사용하고 `cache/sectors/YYYYMMDD.csv`에 캐시합니다.

주요 출력:

- `sector_ret_5d`, `sector_ret_20d`
- `sector_rs_5d`, `sector_rs_20d`
- `sector_breadth`, `sector_turnover_ratio`
- `sector_strength_score`, `sector_market_rank`
- `stock_vs_sector_rs_5d`, `stock_vs_sector_rs_20d`
- `sector_leader_score`, `sector_leader_rank`

## Leader Persistence

최근 며칠 동안 거래대금 상위권이 지속되었는지를 분석 대상 TOP N 종목의 과거 거래대금으로 재구성합니다.

- `leader_persistence_score`
- `leader_persistence_level`: `HIGH / MEDIUM / LOW`
- `turnover_rank_avg_5d`
- `turnover_top20_days_5d`
- `turnover_top50_days_10d`
- `strong_return_days_5d`

`leader_type`:

- `PERSISTENT_LEADER`
- `EMERGING_LEADER`
- `NORMAL`

Persistence가 낮다는 이유만으로 신규 주도주를 자동 탈락시키지 않습니다.

## 최종 상태 판정

- `STRONG_CONFIRMED`: Strong 조건 + 실제 돌파일 경우 Quality 기준 통과 + Context 확인
- `CONFIRMED`: Confirmed 조건 + 실제 돌파일 경우 최소 Quality 기준 통과
- `WATCH`: Timing 부족, Chase Risk 과다, Failed/저품질 돌파, 또는 약한 업종 + 낮은 Persistence
- `REJECT`: 그 외

## Timing

분봉이 있으면:

`DISCOVERED -> BREAKOUT -> PULLBACK_WAIT -> SUPPORT_TEST -> ENTRY_READY`

분봉이 없으면 일봉만으로 눌림/지지/턴을 추측하지 않고 `DAILY_BREAKOUT_PROXY`를 사용합니다.

## Range Performance Engine

`main_range.py`에서는 same-day Analyzer 결과를 만든 뒤 별도 `performance/` 모듈에서 미래 성과를 계산합니다. 미래 데이터는 Leader/Timing/Status 판정에 절대 사용하지 않습니다.

기본 출력:

- `D+1`, `D+5`, `D+20`, `D+60`
- `MFE_D5`, `MAE_D5`
- `MFE_D20`, `MAE_D20`
- `MFE_D60`, `MAE_D60`
- `days_to_MFE_D5/20/60`
- `days_to_MAE_D5/20/60`
- `breakout_hold_D1`, `breakout_hold_D3`
- `failed_within_D3`
- `mfe_capture_D20`
- `excursion_ratio_D20`

MFE/MAE는 종가가 아니라 미래 구간의 실제 `high/low`를 사용하며 D+n은 거래일 row 기준입니다. 완전한 horizon이 없는 최근 신호는 해당 성과값을 비워 두어 기간 길이가 다른 표본을 섞지 않습니다.

장기 Range에서 미래 OHLCV를 후보마다 반복 조회하지 않도록 종목별 전체 Range 데이터를 캐시해 재사용합니다.

## Performance Attribution

Range 실행 후 자동으로 다음 파일을 만듭니다.

```text
results/range_YYYYMMDD_YYYYMMDD/performance/
  overall_summary.csv
  performance_by_status.csv
  performance_by_breakout_quality.csv
  performance_by_leader_type.csv
  performance_by_sector_rank.csv
  performance_by_persistence.csv
  performance_by_persistence_score.csv
  performance_by_leader_score.csv
  performance_by_timing_score.csv
  performance_by_chase_risk.csv
  performance_by_combinations.csv
```

주요 통계:

- count / complete_count
- 평균·중앙값·승률 D+5/D+20/D+60
- D+20 p25 / p75
- 평균·중앙 MFE/MAE D+20
- 평균 excursion ratio / MFE capture
- D+3 돌파 실패율

기본 `min_group_count=20`이며 D+20 완전 표본이 20건 미만이면 `LOW_SAMPLE`로 표시합니다.

## 실행

Screen:

```bat
run_screen.bat
```

Range:

```bat
run_range.bat
```

또는:

```bash
python main_range.py --date-range 20260101~20260831 --top-n 100
```

## 설정

모든 주요 가중치와 임계값은 `config/default.yaml`에서 변경할 수 있습니다.

```text
weights
thresholds
breakout_quality
sector_context
persistence
performance
```

## 테스트

```bash
python -m pytest -q
```

Leader/Timing/Sector/Persistence/Breakout Quality에 더해 Forward Performance와 Attribution 합성 테스트를 포함합니다.
