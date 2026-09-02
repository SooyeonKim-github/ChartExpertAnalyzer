from __future__ import annotations

from .config import CloseBetConfig
from .models import BuyDayGuide


def _valid_below(value: float | None, close: float) -> bool:
    return value is not None and value > 0 and value <= close


def build_buy_day_guide(
    *,
    reference_close: float,
    ma5: float | None,
    nearest_support: float | None,
    cfg: CloseBetConfig,
) -> BuyDayGuide:
    """Build a manual price-action guide for the intended close-bet day.

    V1 deliberately does not analyze same-day intraday candles/orderbook data.
    Instead it turns the prior analysis into concrete prices the user can compare
    with today's live price near the close.
    """
    close = float(reference_close)
    preferred_low = close * (1.0 - cfg.buy_day_soft_drop_pct)
    preferred_high = close * (1.0 + cfg.buy_day_preferred_max_gain_pct)
    chase_above = close * (1.0 + cfg.buy_day_chase_pct)
    hard_cancel = close * (1.0 - cfg.buy_day_hard_cancel_pct)

    supports = [v for v in (ma5, nearest_support) if _valid_below(v, close)]
    structural_hold = max(supports) if supports else preferred_low
    hold_level = max(hard_cancel, structural_hold * (1.0 - cfg.guide_support_buffer_pct))
    cancel_below = max(hard_cancel, hold_level * (1.0 - cfg.guide_support_buffer_pct))

    buy_if = (
        "14:30 이후에도 취소선 위를 유지하고, 기준종가 대비 대략 "
        f"-{cfg.buy_day_soft_drop_pct*100:.0f}%~+{cfg.buy_day_preferred_max_gain_pct*100:.0f}% "
        "범위에서 가격이 무너지지 않으면 종가 진입 검토. 장중 강했던 종목은 오후에도 힘이 유지되는지 직접 확인."
    )
    wait_if = (
        "지지선 부근에서 흔들리거나 오전 강세를 오후에 대부분 반납하면 보류. "
        "다시 지지 회복/안정이 확인될 때만 검토."
    )
    skip_if = (
        f"{cancel_below:,.0f}원 아래로 밀리거나 기준종가 대비 "
        f"+{cfg.buy_day_chase_pct*100:.0f}% 이상 급등해 추격 구간이면 건너뜀. "
        "종가 직전 급등 후 빠르게 밀리는 흐름도 매수하지 않음."
    )
    return BuyDayGuide(
        reference_close=round(close, 2),
        preferred_low=round(preferred_low, 2),
        preferred_high=round(preferred_high, 2),
        hold_level=round(hold_level, 2),
        cancel_below=round(cancel_below, 2),
        chase_above=round(chase_above, 2),
        buy_if=buy_if,
        wait_if=wait_if,
        skip_if=skip_if,
    )
