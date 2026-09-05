from __future__ import annotations

from .models import DeltaResult, EventView


STAGE_RANK = {
    "UNKNOWN": 0,
    "ANNOUNCED": 1,
    "PLANNED": 1,
    "REQUESTED": 2,
    "CONFIRMED": 3,
    "APPROVED": 4,
    "STARTED": 5,
    "COMPLETED": 6,
}

SOURCE_RELIABILITY = {
    "DART": 5,
    "KIND": 5,
    "MOTIR": 4,
    "MSIT": 4,
    "MCEE": 4,
    "MFDS": 4,
    "FSC": 4,
}

GRADE_RELIABILITY = {
    "S": 4,
    "A": 3,
    "B": 2,
    "C": 1,
}


def source_reliability(event: EventView) -> int:
    return max(
        SOURCE_RELIABILITY.get(event.original_source_id, 0),
        GRADE_RELIABILITY.get((event.source_grade or "").upper(), 0),
    )


class DeltaDetector:
    def detect(self, current: EventView, parent: EventView) -> DeltaResult:
        stage_changed = (
            current.event_stage != parent.event_stage
            and current.event_stage not in {"", "UNKNOWN"}
            and parent.event_stage not in {"", "UNKNOWN"}
        )
        stage_progressed = (
            stage_changed
            and current.event_stage != "RELEASED"
            and STAGE_RANK.get(current.event_stage, 0) > STAGE_RANK.get(parent.event_stage, 0)
        )

        current_numbers = set(current.numbers)
        parent_numbers = set(parent.numbers)
        number_changed = current_numbers != parent_numbers and bool(current_numbers or parent_numbers)

        current_companies = set(current.companies)
        parent_companies = set(parent.companies)
        # Only call this a company delta when the family identity is already shared and a new
        # named party appears. Empty metadata on one side is not considered new information.
        shared_identity = bool(
            (set(current.stock_codes) & set(parent.stock_codes))
            or (current_companies & parent_companies)
        )
        company_changed = bool(
            shared_identity
            and current_companies
            and parent_companies
            and (current_companies - parent_companies)
        )

        polarity_changed = (
            current.positive_negative != parent.positive_negative
            and current.positive_negative not in {"", "UNKNOWN"}
            and parent.positive_negative not in {"", "UNKNOWN"}
        )

        current_reliability = source_reliability(current)
        parent_reliability = source_reliability(parent)
        source_reliability_increased = current_reliability > parent_reliability

        source_changed = bool(
            current.original_source_id
            and parent.original_source_id
            and current.original_source_id != parent.original_source_id
        )
        confirmation_source_added = bool(
            current.source_count > parent.source_count
            or current.confirmation_count > parent.confirmation_count
            or (source_changed and current_reliability >= parent_reliability)
        )

        new_information_count = sum(
            int(value)
            for value in (
                stage_changed,
                number_changed,
                company_changed,
                polarity_changed,
                source_reliability_increased,
                confirmation_source_added,
            )
        )

        return DeltaResult(
            stage_changed=stage_changed,
            stage_progressed=stage_progressed,
            number_changed=number_changed,
            company_changed=company_changed,
            polarity_changed=polarity_changed,
            source_reliability_increased=source_reliability_increased,
            confirmation_source_added=confirmation_source_added,
            new_information_count=new_information_count,
            previous_stage=parent.event_stage,
            current_stage=current.event_stage,
            previous_numbers=tuple(parent.numbers),
            current_numbers=tuple(current.numbers),
        )
