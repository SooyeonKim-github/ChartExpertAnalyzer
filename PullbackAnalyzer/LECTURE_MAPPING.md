# Pullback Lecture Mapping

강의록에서 반복된 눌림목 원칙과 V1 정량 구현의 대응표.

| 강의 원칙 | V1 구현 |
|---|---|
| 먼저 강한 상승/기준봉이 있어야 함 | Impulse 15점, `impulse_detector.py` |
| 첫 눌림이 가장 유리 | `Pullback_Sequence`, 1차 6점 / 2차 4점 / 3차 2점 |
| 가격 하락폭보다 하락 성격 | Retracement, midpoint, higher-low, range/ATR contraction |
| 조정 중 거래량 감소 | Pullback volume / impulse volume 비율 |
| 거래량 동반 장대음봉 경계 | `High_Volume_Breakdown`, Hard Reject 가능 |
| 5/10/20/60일선 등은 고정 마법값이 아니라 지지 후보 | MA5/10/20/60/120/224 support confluence |
| 전고점/기준봉/돌파가격도 중요 | BREAKOUT_LEVEL, IMPULSE_OPEN, IMPULSE_MID |
| 볼린저 하단 상승/수렴형 추세 눌림 | `BB_Support` |
| 같은 지지선 반복 테스트 시 약화 | `Support_Touch_Count` |
| 기간조정 + 얕은 하락이 강함 | `Period_Correction` |
| 허리 아래 붕괴 경계 | `Midpoint_Broken` |
| 이격 과대 시 보수적 | `MA20_Extension_Pct`, `Chase_Risk` |
| 다시 살아나는 증거를 확인 | 반전 양봉, MA reclaim, minor-high breakout, volume re-expansion |
| 좋은 눌림과 오늘 타점을 구분 | Score / Timing_Score 분리 |
| 주도섹터/재료/악재 확인 | V1 OHLCV로 추정하지 않고 UNKNOWN interface 유지 |

## Hard Reject

다음은 단순 감점이 아니라 구조 훼손으로 처리한다.

1. 유효한 선행 상승/기준봉 없음
2. 상승폭의 55% 이상 깊은 되돌림
3. 고거래량 장대음봉 + 지지 붕괴
4. MA60 결정적 이탈
5. 최근 major low 이탈
6. 상승 허리 붕괴 후 재돌파 확인 없음

## 독립성

PullbackAnalyzer는 KJB/Swing/MA/Dynamic 점수를 참조하거나 합산하지 않는다.
공용 Universe와 시장 데이터만 공유하며 신호와 결과는 독립적으로 생성한다.
