from __future__ import annotations

import pandas as pd

from .emerging import EmergingTransitionAnalyzer


class EmergingTransitionAnalyzerV12(EmergingTransitionAnalyzer):
    """Extend Emerging reports with lifecycle-vs-price outcome separation.

    `false_emerging` historically meant an EMERGING episode returned to
    DISCOVERY before converting to LEADER. That is a lifecycle outcome, not
    necessarily a failed price outcome. V1.2 keeps the old fields for backward
    compatibility and adds explicit lifecycle and D+20 price labels.
    """

    def events(self, df: pd.DataFrame) -> pd.DataFrame:
        events = super().events(df)
        if events.empty:
            return events

        for horizon in (3, 5, 10):
            old_col = f"false_emerging_within_{horizon}d"
            new_col = f"lifecycle_reversion_within_{horizon}d"
            if old_col in events.columns:
                events[new_col] = events[old_col].fillna(False).astype(bool)

        d20 = pd.to_numeric(events.get("D+20"), errors="coerce")
        if d20 is not None:
            events["price_failure_D20"] = d20.le(0).where(d20.notna())
            events["strong_price_success_D20"] = d20.ge(10).where(d20.notna())
        return events

    @staticmethod
    def _cohort_part(events: pd.DataFrame, cohort: str) -> pd.DataFrame:
        if cohort == "ALL" or "event_type" not in events.columns:
            return events
        return events[events["event_type"].eq(cohort)]

    def summary(self, events: pd.DataFrame) -> pd.DataFrame:
        base = super().summary(events)
        if base.empty:
            return base

        for idx, row in base.iterrows():
            cohort = str(row.get("cohort", "ALL"))
            part = self._cohort_part(events, cohort)
            if part.empty:
                continue

            for horizon in (3, 5, 10):
                col = f"lifecycle_reversion_within_{horizon}d"
                if col in part.columns:
                    base.loc[idx, f"{col}_rate"] = round(
                        float(part[col].fillna(False).mean()) * 100.0, 2
                    )

            for col in ("price_failure_D20", "strong_price_success_D20"):
                if col in part.columns:
                    values = part[col].dropna()
                    if not values.empty:
                        base.loc[idx, f"{col}_rate"] = round(
                            float(values.astype(bool).mean()) * 100.0, 2
                        )
        return base
