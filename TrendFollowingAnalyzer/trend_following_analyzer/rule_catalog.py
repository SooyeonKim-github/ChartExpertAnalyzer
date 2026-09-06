from __future__ import annotations

from dataclasses import asdict, dataclass

LECTURE_CORE = "LECTURE_CORE"
EXPERIMENTAL = "EXPERIMENTAL"
ACTIVE_FILTER = "ACTIVE_FILTER"
BACKTEST_ONLY = "BACKTEST_ONLY"
PLANNED = "PLANNED"


@dataclass(frozen=True)
class RuleSpec:
    key: str
    origin: str
    mode: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


RULE_CATALOG = (
    RuleSpec("trend.ma150_position", LECTURE_CORE, ACTIVE_FILTER, "종가가 30주선(일봉 MA150) 위/아래인지"),
    RuleSpec("trend.ma150_slope", LECTURE_CORE, ACTIVE_FILTER, "30주선(일봉 MA150) 기울기 방향"),
    RuleSpec("trend.slope_threshold_pct", EXPERIMENTAL, BACKTEST_ONLY, "MA150 기울기 최소 절대값 임계치"),
    RuleSpec("stage.transition_context", EXPERIMENTAL, BACKTEST_ONLY, "최근 확정 Stage로 Stage 1/3 전환 구분"),
    RuleSpec("market.ma150_position", LECTURE_CORE, ACTIVE_FILTER, "지수의 30주선(일봉 MA150) 상하 위치"),
    RuleSpec("market.ma150_slope", LECTURE_CORE, ACTIVE_FILTER, "지수 30주선(일봉 MA150) 기울기 방향"),
    RuleSpec("market.slope_threshold_pct", EXPERIMENTAL, BACKTEST_ONLY, "시장 MA150 기울기 최소 절대값 임계치"),
    RuleSpec("market.ma50_alignment", EXPERIMENTAL, BACKTEST_ONLY, "지수 MA50 > MA150 정렬"),
    RuleSpec("market.ma150_distance", EXPERIMENTAL, BACKTEST_ONLY, "지수와 MA150 이격도"),
    RuleSpec("market.52w_high_breadth", LECTURE_CORE, BACKTEST_ONLY, "52주 신고가 비율이 증가하는지 보는 강의 원칙; 현재는 종가 신고가 proxy로 측정하며 실전 필터에는 미사용"),
    RuleSpec("market.52w_high_close_proxy", EXPERIMENTAL, BACKTEST_ONLY, "전체 시장 일별 종가 snapshot으로 계산한 252거래일 종가 신고가 비율"),
    RuleSpec("market.52w_low_breadth", EXPERIMENTAL, BACKTEST_ONLY, "252거래일 종가 신저가 비율 및 신고가-신저가 spread"),
    RuleSpec("market.breadth_velocity", EXPERIMENTAL, BACKTEST_ONLY, "52주 종가 신고가 비율의 5일/20일 평균과 변화량 및 방향"),
    RuleSpec("market.intraday_strength", LECTURE_CORE, BACKTEST_ONLY, "전약후강/전강후약이라는 강의 원칙; 현재는 지수 일봉 OHLC proxy로 측정하며 실전 필터에는 미사용"),
    RuleSpec("market.intraday_daily_ohlc_proxy", EXPERIMENTAL, BACKTEST_ONLY, "지수 시가/고가/저가/종가로 장중 강약을 근사하는 Daily OHLC proxy"),
    RuleSpec("market.intraday_clv_threshold", EXPERIMENTAL, BACKTEST_ONLY, "종가 위치(CLV) 0.70/0.30 기준으로 strong/weak close를 분류"),
    RuleSpec("market.intraday_rolling_ratio", EXPERIMENTAL, BACKTEST_ONLY, "Strong/Weak Close 및 전약후강/전강후약 proxy의 5일/20일 발생 비율"),
    RuleSpec("market.intraday_composite_score", EXPERIMENTAL, BACKTEST_ONLY, "CLV와 당일 몸통 방향을 조합한 설명용 0~100 점수; V1 의사결정에는 미사용"),
    RuleSpec("market.news_reaction", LECTURE_CORE, PLANNED, "호재/악재 민감도"),
)


def rule_catalog_rows() -> list[dict]:
    return [rule.to_dict() for rule in RULE_CATALOG]
