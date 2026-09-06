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
    RuleSpec("market.52w_high_breadth", LECTURE_CORE, PLANNED, "52주 신고가 비율/추세"),
    RuleSpec("market.intraday_strength", LECTURE_CORE, PLANNED, "전약후강/전강후약"),
    RuleSpec("market.news_reaction", LECTURE_CORE, PLANNED, "호재/악재 민감도"),
)


def rule_catalog_rows() -> list[dict]:
    return [rule.to_dict() for rule in RULE_CATALOG]
