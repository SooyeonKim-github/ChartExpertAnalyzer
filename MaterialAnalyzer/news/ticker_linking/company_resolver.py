from __future__ import annotations

from .reference_data import normalize_company


class CompanyResolver:
    """Exact/alias company resolver. Fuzzy matching remains intentionally disabled."""

    def __init__(self, reference_data):
        self.reference_data = reference_data

    def resolve(self, company: str):
        key = normalize_company(company)
        if not key:
            return None
        return self.reference_data.by_company.get(key)

    def status(self, company: str) -> str:
        key = normalize_company(company)
        if not key:
            return "NO_COMPANY"
        override = self.reference_data.company_status_overrides.get(key)
        if override:
            return override[0]
        if key in self.reference_data.ambiguous_companies:
            return "AMBIGUOUS_COMPANY"
        if key in self.reference_data.by_company:
            return "RESOLVED"
        return "COMPANY_NOT_IN_MASTER"
