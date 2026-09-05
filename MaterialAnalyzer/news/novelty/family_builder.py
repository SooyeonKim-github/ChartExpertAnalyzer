from __future__ import annotations

import hashlib

from .models import EventView


def new_family_id(event_id: str) -> str:
    digest = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:16]
    return f"EF_{digest}"


def primary_company(event: EventView) -> str:
    return event.companies[0] if event.companies else ""


def primary_ticker(event: EventView) -> str:
    return event.stock_codes[0] if event.stock_codes else ""


def choose_family_id(event: EventView, parent_family_id: str | None) -> str:
    return parent_family_id or new_family_id(event.event_id)
