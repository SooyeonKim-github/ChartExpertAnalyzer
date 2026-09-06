from __future__ import annotations

from .reference_data import normalize_company


class CompanyResolver:
    """Exact/alias company resolver. Fuzzy matching is intentionally disabled in V1."""

    def __init__(self, reference_data):
        self.reference_data = reference_data

    def resolve(self, company: str):
        key = normalize_company(company)
        if not key:
            return None
        return self.reference_data.by_company.get(key)
