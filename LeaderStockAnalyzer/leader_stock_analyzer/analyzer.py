from __future__ import annotations

from dataclasses import replace

import pandas as pd

from .models import LeaderResult, SignalScore
from .signals import (
    score_chase_risk,
    score_daily_position,
    score_intraday_strength,
    score_ma_structure,
    score_money_flow,
    score_price_strength,
    score_relative_strength,
    score_timing,
)


def _weighted_score(parts: dict[str, SignalScore], weights: dict[str, float]) -> float:
    numerator = 0.0
    denominator = 0.0
    for name, item in parts.items():
        if item.score is None:
            continue
        w = float(weights.get(name, 0.0))
        if w <= 0:
            continue
        numerator += float(item.score) * w
        denominator += w
    return 0.0 if denominator <= 0 else round(numerator / denominator, 2)


def _leader_type(item: LeaderResult, rank: int, cfg: dict) -> str:
    pcfg = cfg.get("persistence", {})
    if item.persistence_available and item.leader_persistence_level == "HIGH":
        return "PERSISTENT_LEADER"

    # EMERGING means today's leadership is strong while recent leadership
    # history is still sparse. This prevents every high-score stock from being
    # labeled emerging and preserves the distinction from persistent leaders.
    if (
        item.persistence_available
        and item.leader_persistence_level == "LOW"
        and item.turnover_top20_days_5d <= int(pcfg.get("emerging_max_top20_days_5d", 2))
        and item.leader_score >= float(pcfg.get("emerging_min_leader_score", 85.0))
        and rank <= int(pcfg.get("emerging_market_rank_max", 10))
    ):
        return "EMERGING_LEADER"
    return "NORMAL"


def _status(item: LeaderResult, cfg: dict) -> str:
    t = cfg["thresholds"]
    scfg = cfg.get("sector_context", {})

    base_strong = (
        item.leader_score >= float(t["strong_confirmed_leader"])
        and item.timing_score >= float(t["strong_confirmed_timing"])
        and item.chase_risk < float(t["max_confirmed_chase_risk"])
        and item.market_leader_rank <= int(t["strong_rank_max"])
    )
    base_confirmed = (
        item.leader_score >= float(t["confirmed_leader"])
        and item.timing_score >= float(t["confirmed_timing"])
        and item.chase_risk < float(t["max_confirmed_chase_risk"])
    )

    sector_available = bool(item.sector_context_available and item.sector_context_reliable)
    sector_support = (
        sector_available
        and item.sector_market_rank > 0
        and item.sector_market_rank <= int(scfg.get("strong_sector_rank_max", 5))
        and item.sector_leader_rank > 0
        and item.sector_leader_rank <= int(scfg.get("strong_sector_leader_rank_max", 3))
    )
    sector_weak = (
        sector_available
        and item.sector_market_rank >= int(scfg.get("weak_sector_rank_min", 15))
    )
    persistent_support = bool(
        item.persistence_available and item.leader_persistence_level == "HIGH"
    )
    emerging_support = item.leader_type == "EMERGING_LEADER"
    context_available = sector_available or item.persistence_available

    # Strong candidates need at least one context confirmation when context
    # exists. A newly emerging leader is a valid confirmation even though its
    # persistence is low by definition.
    if base_strong:
        if not context_available or sector_support or persistent_support or emerging_support:
            return "STRONG_CONFIRMED"

    if base_confirmed:
        # Weak sector + low persistence is intentionally downgraded to WATCH,
        # except for a genuine emerging leader.
        if (
            sector_weak
            and item.persistence_available
            and item.leader_persistence_level == "LOW"
            and not emerging_support
        ):
            return "WATCH"
        return "CONFIRMED"

    if item.leader_score >= float(t["watch_leader"]):
        return "WATCH"
    return "REJECT"


def _build_signal(result: LeaderResult) -> str:
    reasons: list[str] = []
    if result.trading_value_rank <= 10:
        reasons.append(f"거래대금 {result.trading_value_rank}위")
    if result.return_pct >= 10:
        reasons.append("상승률 10%+")
    elif result.return_pct >= 5:
        reasons.append("상승률 5%+")
    if result.high_20d_break:
        reasons.append("20일 고점 돌파")
    elif result.high_10d_break:
        reasons.append("10일 고점 돌파")
    if result.previous_high_break:
        reasons.append("전고점 돌파")
    if result.market_relative_strength is not None and result.market_relative_strength >= 3:
        reasons.append("시장 대비 강세")
    if result.sector_context_available and result.sector_context_reliable:
        if 0 < result.sector_market_rank <= 5:
            reasons.append(f"강한 업종 {result.sector_market_rank}위")
        if 0 < result.sector_leader_rank <= 3:
            reasons.append(f"업종 내 {result.sector_leader_rank}위")
    if result.leader_type == "PERSISTENT_LEADER":
        reasons.append("주도 지속")
    elif result.leader_type == "EMERGING_LEADER":
        reasons.append("신규 주도 등장")
    if result.entry_state == "ENTRY_READY":
        reasons.append("돌파 후 눌림·지지·턴")
    elif result.entry_state == "DAILY_BREAKOUT_PROXY":
        reasons.append("일봉 돌파 강도")
    if result.chase_risk >= 60:
        reasons.append("추격위험 높음")
    return " · ".join(reasons) if reasons else "주도 강도 관찰"


class LeaderStockAnalyzer:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def analyze_one(
        self,
        *,
        scan_date: str,
        ticker: str,
        name: str,
        market: str,
        price: float,
        return_pct: float,
        trading_value: float,
        trading_value_rank: int,
        universe_size: int,
        daily: pd.DataFrame,
        intraday: pd.DataFrame | None,
        market_return_pct: float | None,
    ) -> LeaderResult:
        money = score_money_flow(trading_value, trading_value_rank, universe_size, daily, self.cfg)
        price_sig = score_price_strength(return_pct)
        position = score_daily_position(daily)
        ma_sig = score_ma_structure(daily)
        intra = score_intraday_strength(intraday if intraday is not None else pd.DataFrame(), self.cfg)
        rs = score_relative_strength(return_pct, market_return_pct)
        chase = score_chase_risk(daily, return_pct)
        timing = score_timing(daily, intraday, position.details.get("breakout_reference"))

        parts = {
            "money_flow": money,
            "price_strength": price_sig,
            "daily_position": position,
            "intraday_strength": intra,
            "relative_strength": rs,
            "ma_structure": ma_sig,
        }
        leader_score = _weighted_score(parts, self.cfg["weights"])
        p = position.details
        rs_pct = rs.details.get("rs_pct") if rs.score is not None else None
        return LeaderResult(
            scan_date=scan_date,
            ticker=str(ticker).zfill(6),
            name=name,
            market=market,
            status="PENDING",
            leader_score=leader_score,
            timing_score=round(float(timing.score), 2),
            market_leader_rank=0,
            trading_value_rank=int(trading_value_rank),
            price=float(price),
            return_pct=float(return_pct),
            trading_value=float(trading_value),
            money_flow_score=money.score,
            price_strength_score=price_sig.score,
            daily_position_score=position.score,
            intraday_strength_score=intra.score,
            relative_strength_score=rs.score,
            ma_structure_score=ma_sig.score,
            chase_risk=float(chase.score or 0.0),
            entry_state=timing.entry_state,
            timing_source=timing.source,
            intraday_available=intra.score is not None,
            high_10d_break=bool(p.get("high_10d_break", False)),
            high_20d_break=bool(p.get("high_20d_break", False)),
            high_52d_break=bool(p.get("high_52d_break", False)),
            previous_high_break=bool(p.get("previous_high_break", False)),
            close_20d_high=bool(p.get("close_20d_high", False)),
            volume_ratio_20=money.details.get("volume_ratio_20"),
            market_relative_strength=rs_pct,
            signal="",
            details={
                "money_flow": money.details,
                "price_strength": price_sig.details,
                "daily_position": position.details,
                "intraday_strength": intra.details,
                "relative_strength": rs.details,
                "ma_structure": ma_sig.details,
                "timing": timing.details,
                "chase_risk": chase.details,
            },
        )

    def finalize(self, results: list[LeaderResult]) -> list[LeaderResult]:
        ranked = sorted(results, key=lambda x: (-x.leader_score, x.trading_value_rank, x.ticker))
        out: list[LeaderResult] = []
        for idx, item in enumerate(ranked, start=1):
            typed = replace(item, market_leader_rank=idx, leader_type=_leader_type(item, idx, self.cfg))
            status = _status(typed, self.cfg)
            updated = replace(typed, status=status)
            updated = replace(updated, signal=_build_signal(updated))
            out.append(updated)
        return out
