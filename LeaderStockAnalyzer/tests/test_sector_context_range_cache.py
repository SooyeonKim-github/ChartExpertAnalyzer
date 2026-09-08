from __future__ import annotations

from pathlib import Path

import pandas as pd

from leader_stock_analyzer.screen import _sector_map_for_scan


class _FakeProvider:
    def __init__(self, root: Path, responses: list[dict[str, str]]):
        self.sector_cache_root = root
        self.sector_cache_root.mkdir(parents=True, exist_ok=True)
        self.responses = list(responses)
        self.calls: list[str] = []

    def get_sector_map(self, scan_date: str) -> dict[str, str]:
        self.calls.append(scan_date)
        if not self.responses:
            return {}
        return dict(self.responses.pop(0))


def _cfg(max_stale: int = 62) -> dict:
    return {"sector_context": {"membership_max_staleness_days": max_stale}}


def test_sector_membership_is_reused_within_same_month(tmp_path: Path) -> None:
    provider = _FakeProvider(tmp_path, [{"005930": "전기전자"}])

    first = _sector_map_for_scan(provider, "20260102", _cfg())
    second = _sector_map_for_scan(provider, "20260130", _cfg())

    assert first == {"005930": "전기전자"}
    assert second == first
    assert provider.calls == ["20260102"]


def test_failed_monthly_refresh_uses_only_prior_snapshot(tmp_path: Path) -> None:
    provider = _FakeProvider(
        tmp_path,
        [
            {"005930": "전기전자"},
            {},
        ],
    )

    january = _sector_map_for_scan(provider, "20260102", _cfg())
    february = _sector_map_for_scan(provider, "20260202", _cfg())

    assert january == {"005930": "전기전자"}
    assert february == january
    assert provider.calls == ["20260102", "20260202"]


def test_disk_fallback_never_uses_future_snapshot(tmp_path: Path) -> None:
    pd.DataFrame(
        [{"ticker": "005930", "sector": "과거업종"}]
    ).to_csv(tmp_path / "20260102.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [{"ticker": "005930", "sector": "미래업종"}]
    ).to_csv(tmp_path / "20260302.csv", index=False, encoding="utf-8-sig")

    provider = _FakeProvider(tmp_path, [{}])
    mapping = _sector_map_for_scan(provider, "20260202", _cfg())

    assert mapping == {"005930": "과거업종"}
    assert provider.calls == ["20260202"]


def test_too_old_snapshot_is_not_reused(tmp_path: Path) -> None:
    pd.DataFrame(
        [{"ticker": "005930", "sector": "오래된업종"}]
    ).to_csv(tmp_path / "20250102.csv", index=False, encoding="utf-8-sig")

    provider = _FakeProvider(tmp_path, [{}])
    mapping = _sector_map_for_scan(provider, "20260202", _cfg(max_stale=62))

    assert mapping == {}
