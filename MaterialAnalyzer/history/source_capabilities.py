from __future__ import annotations


RANGE_API = "RANGE_API"
PAGED_LIST = "PAGED_LIST"
LIVE_ONLY = "LIVE_ONLY"
UNSUPPORTED = "UNSUPPORTED"

SOURCE_CAPABILITIES = {
    "DART": RANGE_API,
    "KIND": LIVE_ONLY,
    "MOTIR": PAGED_LIST,
    "MSIT": PAGED_LIST,
    "MCEE": PAGED_LIST,
    "MFDS": PAGED_LIST,
    "FSC": PAGED_LIST,
}


def historical_mode(source_id: str) -> str:
    return SOURCE_CAPABILITIES.get(str(source_id or "").upper(), UNSUPPORTED)
