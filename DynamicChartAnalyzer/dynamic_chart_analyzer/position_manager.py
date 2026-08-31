from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .config import StrategyConfig

Side = Literal["LONG", "SHORT"]


@dataclass
class EntryPlan:
    capital_base: float
    stage1_amount: float
    stage2_amount: float
    stage3_amount: float
    risk_capped: bool = False
    stop_distance_ratio: float | None = None

    @property
    def total_amount(self) -> float:
        return self.stage1_amount + self.stage2_amount + self.stage3_amount


def build_entry_plan(cfg: StrategyConfig, entry_price: float | None = None, stop_price: float | None = None) -> EntryPlan:
    """Return a 1:2:7 staged allocation.

    Default: 10,000,000 KRW -> 1,000,000 / 2,000,000 / 7,000,000.
    Optional 2% risk mode first caps the maximum trade notional by
    account_risk / stop_distance, then splits that capped notional 1:2:7.
    """
    cfg.validate()
    capital_base = cfg.total_capital
    risk_capped = False
    stop_distance_ratio = None

    if cfg.use_two_percent_risk_cap and entry_price and stop_price and entry_price > 0:
        stop_distance_ratio = abs(entry_price - stop_price) / entry_price
        if stop_distance_ratio > 0:
            risk_cap = cfg.total_capital * cfg.max_account_risk_ratio / stop_distance_ratio
            capital_base = min(capital_base, risk_cap)
            risk_capped = capital_base < cfg.total_capital

    return EntryPlan(
        capital_base=capital_base,
        stage1_amount=capital_base * cfg.stage1_ratio,
        stage2_amount=capital_base * cfg.stage2_ratio,
        stage3_amount=capital_base * cfg.stage3_ratio,
        risk_capped=risk_capped,
        stop_distance_ratio=stop_distance_ratio,
    )


@dataclass
class PositionLot:
    stage: int
    amount_krw: float
    entry_price: float
    quantity: float


@dataclass
class PositionState:
    side: Side | None = None
    stage: int = 0
    invested_amount: float = 0.0
    exited_ratio: float = 0.0
    entry_plan: EntryPlan | None = None
    lots: list[PositionLot] = field(default_factory=list)
    stop_price: float | None = None
    reference_target_price: float | None = None
    realized_pnl_krw: float = 0.0
    events: list[dict] = field(default_factory=list)

    @property
    def total_quantity(self) -> float:
        return sum(l.quantity for l in self.lots)

    @property
    def weighted_entry_price(self) -> float | None:
        q = self.total_quantity
        if q <= 0:
            return None
        return sum(l.entry_price * l.quantity for l in self.lots) / q

    def reset(self) -> None:
        self.side = None
        self.stage = 0
        self.invested_amount = 0.0
        self.exited_ratio = 0.0
        self.entry_plan = None
        self.lots = []
        self.stop_price = None
        self.reference_target_price = None

    def _amount_for_stage(self, stage: int) -> float:
        if self.entry_plan is None:
            raise RuntimeError("entry_plan is not initialized")
        return {1: self.entry_plan.stage1_amount, 2: self.entry_plan.stage2_amount, 3: self.entry_plan.stage3_amount}[stage]

    def _pnl_per_share(self, exit_price: float, entry_price: float) -> float:
        return exit_price - entry_price if self.side == "LONG" else entry_price - exit_price

    def enter_stage(
        self,
        side: Side,
        stage: int,
        date,
        price: float,
        plan: EntryPlan,
        stop_price: float | None = None,
        reference_rr: float | None = None,
    ) -> dict | None:
        if self.side is None:
            if stage != 1:
                return None
            self.side = side
            self.entry_plan = plan
            self.stop_price = stop_price
            if stop_price is not None and reference_rr is not None:
                risk = abs(price - stop_price)
                self.reference_target_price = price + risk * reference_rr if side == "LONG" else price - risk * reference_rr

        if self.side != side or stage != self.stage + 1:
            return None

        amount = self._amount_for_stage(stage)
        qty = 0.0 if price <= 0 else amount / price
        self.lots.append(PositionLot(stage=stage, amount_krw=amount, entry_price=price, quantity=qty))
        self.stage = stage
        self.invested_amount += amount

        event = {
            "date": date,
            "action": f"{side}_ENTRY_STAGE_{stage}",
            "price": float(price),
            "amount_krw": float(amount),
            "quantity": float(qty),
            "cumulative_invested_krw": float(self.invested_amount),
            "weighted_entry_price": float(self.weighted_entry_price or price),
            "stop_price": self.stop_price,
            "reference_target_price": self.reference_target_price,
            "risk_capped": bool(plan.risk_capped),
            "stage": stage,
        }
        self.events.append(event)
        return event

    def _reduce_quantity(self, qty_to_exit: float, exit_price: float) -> float:
        remaining = qty_to_exit
        pnl = 0.0
        new_lots: list[PositionLot] = []
        for lot in self.lots:
            if remaining <= 1e-12:
                new_lots.append(lot)
                continue
            take = min(lot.quantity, remaining)
            pnl += self._pnl_per_share(exit_price, lot.entry_price) * take
            lot_remaining = lot.quantity - take
            remaining -= take
            if lot_remaining > 1e-12:
                new_lots.append(
                    PositionLot(
                        stage=lot.stage,
                        amount_krw=lot.amount_krw * (lot_remaining / lot.quantity),
                        entry_price=lot.entry_price,
                        quantity=lot_remaining,
                    )
                )
        self.lots = new_lots
        self.realized_pnl_krw += pnl
        return pnl

    def exit_part(self, exit_stage: int, date, price: float, reason: str | None = None) -> dict | None:
        if self.side is None or self.stage == 0 or self.total_quantity <= 0:
            return None

        target_ratio = {1: 0.10, 2: 0.20, 3: 0.70}[exit_stage]
        cumulative_target = {1: 0.10, 2: 0.30, 3: 1.00}[exit_stage]
        if self.exited_ratio >= cumulative_target - 1e-12:
            return None

        # 1:2:7 refers to the original fully-entered position. If a position is being
        # aborted before Stage 3, use exit_all() instead of this staged exit method.
        original_quantity = self.total_quantity / max(1e-12, 1.0 - self.exited_ratio)
        qty = min(self.total_quantity, original_quantity * target_ratio)
        pnl = self._reduce_quantity(qty, price)
        self.exited_ratio += target_ratio

        event = {
            "date": date,
            "action": f"{self.side}_EXIT_STAGE_{exit_stage}",
            "reason": reason or f"EXIT_STAGE_{exit_stage}",
            "price": float(price),
            "quantity": float(qty),
            "market_value_krw": float(qty * price),
            "realized_pnl_krw": float(pnl),
            "cumulative_realized_pnl_krw": float(self.realized_pnl_krw),
            "remaining_ratio": max(0.0, 1.0 - self.exited_ratio),
            "stage": exit_stage,
        }
        self.events.append(event)
        if exit_stage == 3 or self.exited_ratio >= 0.999999 or self.total_quantity <= 1e-12:
            self.reset()
        return event

    def exit_all(self, date, price: float, reason: str) -> dict | None:
        if self.side is None or self.total_quantity <= 0:
            return None
        side = self.side
        qty = self.total_quantity
        pnl = self._reduce_quantity(qty, price)
        event = {
            "date": date,
            "action": f"{side}_EXIT_ALL",
            "reason": reason,
            "price": float(price),
            "quantity": float(qty),
            "market_value_krw": float(qty * price),
            "realized_pnl_krw": float(pnl),
            "cumulative_realized_pnl_krw": float(self.realized_pnl_krw),
            "remaining_ratio": 0.0,
            "stage": self.stage,
        }
        self.events.append(event)
        self.reset()
        return event

    def unrealized_pnl(self, price: float) -> float:
        if self.side is None:
            return 0.0
        return sum(self._pnl_per_share(price, lot.entry_price) * lot.quantity for lot in self.lots)
